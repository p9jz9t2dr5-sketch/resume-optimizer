"""Local upload store helpers.

Uploaded files live in ``settings.UPLOAD_DIR`` on the server, but they are
*served* from the ``/uploads`` mount declared in ``app.main``. Anything handed
to the frontend must therefore be in URL form: the client prefixes it with
API_BASE, so a server-side filesystem path (``/data/uploads/x.png``, or a
Windows path with backslashes) would 404 in the browser once UPLOAD_DIR is
anything other than the default ``./uploads``.

Keeping the two directions in one place means the URL prefix is defined once.
"""

import os

# Must stay in sync with `app.mount("/uploads", ...)` in app.main.
UPLOAD_URL_PREFIX = "./uploads"


def upload_url(filename: str) -> str:
    """Client-facing URL for a file stored under UPLOAD_DIR."""
    return f"{UPLOAD_URL_PREFIX}/{filename}"


def stored_filename(url_or_path: str) -> str:
    """Filename of a stored file, given either its URL or a legacy filesystem path."""
    return os.path.basename((url_or_path or "").replace("\\", "/"))
