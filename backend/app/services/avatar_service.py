import base64
import io
import os
import uuid
from typing import Optional

from PIL import Image, ImageOps, ImageStat

from app.config import get_settings
from app.services.llm_service import llm_service

settings = get_settings()

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# Avatar bbox detection uses a normalized image size so that Qwen-VL-Max's
# bounding box coordinates map back to a known scale. Empirically (Qwen-VL
# silently rescales anything bigger than ~800x800 to fit a ~800-long-edge
# budget) — if we don't resize ourselves, the returned coords are in an
# unknown inner space and the crop lands in the wrong region (often blank).
_AVATAR_QUERY_MAX_EDGE = 800

# How aggressive to trim whitespace around the cropped avatar.
# (mean_threshold, stddev_threshold) — borders averaging whiter than this
# are considered "background" and get cropped away.
_WHITE_MEAN_THRESHOLD = 235.0
_WHITE_STDDEV_THRESHOLD = 12.0


def _to_px(value: float, dim: int) -> int:
    """Qwen-VL-Max returns absolute pixel coordinates directly (verified
    empirically: for a 2469×3496 image it returned x=87, y=60, width=192,
    height=234 — that is the head/shoulders pixel box, not 8.7%/6.0%/etc.).

    The old code treated these as percentages and produced wildly offset
    crops (e.g. x=87 → 2148 px), which then either got blank-checked or
    cropped the wrong region entirely. We now trust absolute pixels.
    """
    return int(round(value))


def _is_blank_image(path: str, mean_max: float = 235.0, stddev_max: float = 25.0) -> bool:
    """Heuristic: a real headshot is colorful and has varied pixel values.
    An empty circular placeholder, a logo, or a section of pure white page will
    have high mean and low stddev. Returns True when the file looks blank."""
    try:
        with Image.open(path) as im:
            gray = im.convert("L")
            stat = ImageStat.Stat(gray)
            mean, stddev = stat.mean[0], stat.stddev[0]
        return mean >= mean_max or stddev <= stddev_max
    except Exception:
        return True  # treat unreadable as blank


def _trim_whitespace_bbox(crop: Image.Image) -> tuple[int, int, int, int]:
    """Re-tighten the crop by scanning each edge from the outside in and
    chopping off any row/column that is essentially blank. Returns the tighter
    (left, top, right, bottom) within the original crop. Always keeps at least
    1 px on each side so we never return an empty box.
    """
    gray = crop.convert("L")
    px = gray.load()
    W, H = crop.size

    # Mark each row/column as "blank" if every pixel in that row/col is blank.
    def is_blank_row(y: int) -> bool:
        s = 0
        ss = 0
        n = 0
        for x in range(W):
            v = px[x, y]
            s += v
            ss += v * v
            n += 1
        mean = s / n
        stddev = (ss / n - mean * mean) ** 0.5
        return mean >= _WHITE_MEAN_THRESHOLD and stddev <= _WHITE_STDDEV_THRESHOLD

    def is_blank_col(x: int) -> bool:
        s = 0
        ss = 0
        n = 0
        for y in range(H):
            v = px[x, y]
            s += v
            ss += v * v
            n += 1
        mean = s / n
        stddev = (ss / n - mean * mean) ** 0.5
        return mean >= _WHITE_MEAN_THRESHOLD and stddev <= _WHITE_STDDEV_THRESHOLD

    top = 0
    while top < H - 1 and is_blank_row(top):
        top += 1
    bottom = H - 1
    while bottom > top and is_blank_row(bottom):
        bottom -= 1
    left = 0
    while left < W - 1 and is_blank_col(left):
        left += 1
    right = W - 1
    while right > left and is_blank_col(right):
        right -= 1
    return left, top, right + 1, bottom + 1


def _resolve_avatar_url(avatar_url: Optional[str]) -> Optional[str]:
    """Server-side safeguard used in API responses.

    Any stored avatar URL that points to a missing file, or to a file whose
    pixels are blank (empty template placeholder), is collapsed to None. This
    means the React template renders the header without an empty circle
    regardless of whether the DB still has stale records from before the
    blank-detection fix.
    """
    if not avatar_url:
        return None
    # avatar_url is stored as e.g. "./uploads\\avatar_xxx.png" on Windows.
    # Match by basename so we don't double-join with UPLOAD_DIR (which already
    # lives inside the avatar_url).
    fname = os.path.basename(avatar_url.replace("\\", "/"))
    if not fname:
        return None
    full = os.path.normpath(os.path.join(settings.UPLOAD_DIR, fname))
    if not os.path.exists(full):
        return None
    if _is_blank_image(full):
        return None
    return avatar_url


async def extract_avatar(original_path: str) -> Optional[str]:
    """Extract and crop the person's avatar from an uploaded image resume.

    Returns a stored relative path like './uploads/avatar_<uuid>.png' (consumable
    by the frontend exactly like original_file_url), or None when the file isn't an
    image, the vision key is missing, no avatar is detected, the cropped region
    is blank (empty placeholder), or any step fails.
    Best-effort: failures never block the upload.
    """
    ext = os.path.splitext(original_path)[1].lower()
    if ext not in IMAGE_EXTS:
        return None

    if not settings.DASHSCOPE_API_KEY:
        return None

    avatar_path: Optional[str] = None
    try:
        # 1. Read original image to get its true dimensions.
        with Image.open(original_path) as orig:
            orig_rgb = orig.convert("RGB")
            orig_W, orig_H = orig_rgb.size

        # 2. Build a resized copy (long edge <= _AVATAR_QUERY_MAX_EDGE) so Qwen-VL
        #    sees a known coordinate space. We then tell it the resized (W, H) and
        #    map the bbox back to the original image. This avoids the silent
        #    rescale Qwen-VL does internally, which previously made its bbox
        #    values land in the wrong region of the high-res input.
        scale = _AVATAR_QUERY_MAX_EDGE / float(max(orig_W, orig_H))
        if scale < 1.0:
            new_W = max(1, int(round(orig_W * scale)))
            new_H = max(1, int(round(orig_H * scale)))
        else:
            new_W, new_H = orig_W, orig_H
        resize_factor = orig_W / float(new_W)  # same for height (proportional)

        buf = io.BytesIO()
        with Image.open(original_path) as im:
            im = im.convert("RGB")
            if (im.size[0], im.size[1]) != (new_W, new_H):
                im = im.resize((new_W, new_H), Image.LANCZOS)
            im.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("ascii")

        # 3. Call Qwen-VL with the resized image and explicit (W, H) hint.
        bbox = await llm_service.detect_avatar_bbox_with_size(
            image_b64=b64,
            mime="image/png",
            width=new_W,
            height=new_H,
        )
        if not bbox:
            return None

        # 4. Map bbox from resized coords back to original coords.
        x = bbox["x"] * resize_factor
        y = bbox["y"] * resize_factor
        w = bbox["width"] * resize_factor
        h = bbox["height"] * resize_factor

        with Image.open(original_path) as img:
            img = img.convert("RGB")
            W, H = img.size

            x = max(0, min(int(round(x)), W - 1))
            y = max(0, min(int(round(y)), H - 1))
            right = max(x + 1, min(int(round(x + w)), W))
            bottom = max(y + 1, min(int(round(y + h)), H))

            # Sanity: keep only plausibly-sized crops (5%–100% of either dim).
            if (right - x) < 0.05 * W or (bottom - y) < 0.05 * H:
                return None

            crop = img.crop((x, y, right, bottom))

            # Tighten the crop by removing background whitespace around the
            # head/shoulders. The model likes to leave generous padding.
            crop = crop.crop(_trim_whitespace_bbox(crop))
            if crop.size[0] < 0.02 * W or crop.size[1] < 0.02 * H:
                return None

            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            avatar_filename = f"avatar_{uuid.uuid4().hex}.png"
            avatar_path = os.path.join(settings.UPLOAD_DIR, avatar_filename)
            crop.save(avatar_path, "PNG")

        # Discard blank crops (empty placeholders, pure-white regions,
        # thin outlines). Otherwise the template renders an empty circle.
        if _is_blank_image(avatar_path):
            try:
                os.remove(avatar_path)
            except OSError:
                pass
            return None

        # Store with the same relative form as original_file_url so the frontend
        # URL-building logic (strip leading "./", forward-slash backslashes) works.
        return os.path.join(settings.UPLOAD_DIR, avatar_filename)
    except Exception:
        if avatar_path and os.path.exists(avatar_path):
            try:
                os.remove(avatar_path)
            except OSError:
                pass
        return None


# ---------------------------------------------------------------------------
# User profile avatars (uploaded by the user from the header menu) — unlike
# extract_avatar() above there is no LLM involved: the image is centre-cropped
# to a square, downscaled and re-encoded as PNG.
# ---------------------------------------------------------------------------

USER_AVATAR_SIZE = 256


def store_user_avatar(data: bytes) -> str:
    """Normalise an uploaded profile picture and write it under UPLOAD_DIR.

    Returns a stored relative path like './uploads/avatar_<uuid>.png', matching
    the form used elsewhere so the frontend can prefix it with API_BASE.
    Raises ValueError when the bytes are not a decodable image.
    """
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise ValueError("无法识别该图片文件，请上传 PNG / JPG / WebP 格式")

    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img = ImageOps.fit(img, (USER_AVATAR_SIZE, USER_AVATAR_SIZE), Image.LANCZOS)

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    avatar_filename = f"avatar_{uuid.uuid4().hex}.png"
    img.save(os.path.join(settings.UPLOAD_DIR, avatar_filename), "PNG", optimize=True)

    return os.path.join(settings.UPLOAD_DIR, avatar_filename)


def delete_stored_file(stored_url: Optional[str]) -> None:
    """Best-effort removal of a file we previously stored under UPLOAD_DIR.

    Only the basename is honoured, so a tampered value in the DB can never
    delete anything outside the upload directory.
    """
    if not stored_url:
        return
    filename = os.path.basename(stored_url.replace("\\", "/"))
    if not filename:
        return
    path = os.path.normpath(os.path.join(settings.UPLOAD_DIR, filename))
    root = os.path.normpath(settings.UPLOAD_DIR)
    if os.path.dirname(path) != root:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
