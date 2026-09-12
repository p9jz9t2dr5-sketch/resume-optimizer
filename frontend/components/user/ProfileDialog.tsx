"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, Loader2, Trash2, X } from "lucide-react";
import { mediaUrl } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { useToast } from "@/stores/toastStore";
import UserAvatar, { displayNameOf } from "./UserAvatar";

const MAX_NAME_LENGTH = 8;
const MAX_AVATAR_BYTES = 5 * 1024 * 1024;
const ALLOWED_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/webp"];

interface ProfileDialogProps {
  open: boolean;
  onClose: () => void;
}

export default function ProfileDialog({ open, onClose }: ProfileDialogProps) {
  const user = useAuthStore((s) => s.user);
  const updateProfile = useAuthStore((s) => s.updateProfile);
  const uploadAvatar = useAuthStore((s) => s.uploadAvatar);
  const removeAvatar = useAuthStore((s) => s.removeAvatar);
  const toast = useToast();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Re-seed the form every time the dialog opens.
  useEffect(() => {
    if (!open) return;
    // The email-prefix fallback can be longer than the limit, so cap only that
    // derived default — a name the user actually saved is shown as-is.
    const saved = user?.display_name?.trim();
    setName(saved || displayNameOf(user).slice(0, MAX_NAME_LENGTH));
    setFile(null);
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Release the object URL of a preview that is being replaced or dropped.
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview]
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, saving, onClose]);

  if (!open) return null;

  const handlePickFile = (picked: File | null) => {
    if (!picked) return;
    if (!ALLOWED_TYPES.includes(picked.type)) {
      toast.error("仅支持 PNG / JPG / WebP 格式的图片");
      return;
    }
    if (picked.size > MAX_AVATAR_BYTES) {
      toast.error("图片不能超过 5MB");
      return;
    }
    setFile(picked);
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(picked);
    });
  };

  const handleSave = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      toast.error("昵称不能为空");
      return;
    }
    if (trimmed.length > MAX_NAME_LENGTH) {
      toast.error(`昵称最多 ${MAX_NAME_LENGTH} 个字`);
      return;
    }

    setSaving(true);
    try {
      if (file) await uploadAvatar(file);
      await updateProfile(trimmed);
      toast.success("资料已更新");
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败，请稍后重试");
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveAvatar = async () => {
    setSaving(true);
    try {
      await removeAvatar();
      setFile(null);
      setPreview((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      toast.success("头像已移除");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "移除失败，请稍后重试");
    } finally {
      setSaving(false);
    }
  };

  const previewSrc = preview ?? mediaUrl(user?.avatar_url);
  const shownName = name.trim() || displayNameOf(user);

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={() => !saving && onClose()}
      />

      <div className="relative w-full max-w-md rounded-2xl border border-border bg-bg-card p-6 shadow-2xl shadow-black/20">
        <button
          type="button"
          onClick={() => !saving && onClose()}
          aria-label="关闭"
          className="absolute right-4 top-4 rounded-lg p-1.5 text-text-muted transition-colors hover:bg-accent-soft hover:text-text-primary"
        >
          <X className="h-4 w-4" />
        </button>

        <h3 className="text-base font-semibold text-text-primary">编辑资料</h3>
        <p className="mt-1 text-sm text-text-secondary">换一个头像，或者改个昵称。</p>

        <div className="mt-6 flex items-center gap-4">
          <UserAvatar
            src={previewSrc}
            name={shownName}
            className="h-16 w-16"
            textClassName="text-xl"
          />

          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={saving}
                className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-sm disabled:opacity-50"
              >
                <Camera className="h-4 w-4" />
                上传头像
              </button>
              {(user?.avatar_url || file) && (
                <button
                  type="button"
                  onClick={handleRemoveAvatar}
                  disabled={saving}
                  className="flex items-center gap-1.5 rounded-xl border border-border px-3 py-1.5 text-sm text-text-secondary transition-colors hover:border-danger/40 hover:text-danger disabled:opacity-50"
                >
                  <Trash2 className="h-4 w-4" />
                  移除
                </button>
              )}
            </div>
            <p className="text-xs text-text-muted">PNG / JPG / WebP，5MB 以内</p>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(e) => {
              handlePickFile(e.target.files?.[0] ?? null);
              e.target.value = "";
            }}
          />
        </div>

        <div className="mt-6">
          <label htmlFor="profile-display-name" className="text-sm font-medium text-text-primary">
            昵称
          </label>
          <input
            id="profile-display-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSave();
            }}
            maxLength={MAX_NAME_LENGTH}
            disabled={saving}
            placeholder="给自己起个名字"
            className="glass-input mt-2 w-full px-3.5 py-2.5 text-sm"
          />
          <p className="mt-1.5 text-xs text-text-muted">最多 {MAX_NAME_LENGTH} 个字</p>
          <p className="mt-1 text-xs text-text-muted">登录邮箱：{user?.email}</p>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="btn-ghost px-4 py-2 text-sm disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="btn-gradient flex items-center gap-2 px-5 py-2 text-sm disabled:opacity-60"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
