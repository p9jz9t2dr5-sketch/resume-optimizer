"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronDown, LayoutDashboard, LogOut, Settings2 } from "lucide-react";
import { mediaUrl } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import UserAvatar, { displayNameOf } from "./UserAvatar";
import ProfileDialog from "./ProfileDialog";

/**
 * Avatar button + dropdown used in the top-right corner of both headers
 * (landing page and the shared Navbar). Renders nothing for signed-out users —
 * callers keep their own "登录 / 立即开始" call to action in that case.
 */
export default function UserMenu() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const router = useRouter();

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;

  const name = displayNameOf(user);
  const avatarSrc = mediaUrl(user.avatar_url);

  const handleLogout = () => {
    setOpen(false);
    logout();
    router.push("/");
  };

  const menuItemClass =
    "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-text-secondary transition-colors hover:bg-accent-soft hover:text-accent";

  return (
    <div className="relative" ref={boxRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="账号菜单"
        className="flex items-center gap-1.5 rounded-full border border-border bg-bg-card py-0.5 pl-0.5 pr-1.5 transition-colors hover:border-accent/40 hover:bg-accent-soft"
      >
        <UserAvatar src={avatarSrc} name={name} className="h-7 w-7" textClassName="text-xs" />
        <span className="hidden max-w-[7rem] truncate text-sm font-medium text-text-primary sm:block">
          {name}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 text-text-muted transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-60 overflow-hidden rounded-xl border border-border bg-bg-card shadow-xl shadow-black/10"
        >
          <div className="flex items-center gap-3 border-b border-border px-4 py-3">
            <UserAvatar
              src={avatarSrc}
              name={name}
              className="h-10 w-10"
              textClassName="text-base"
            />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-text-primary">{name}</p>
              <p className="truncate text-xs text-text-secondary">{user.email}</p>
            </div>
          </div>

          <div className="p-1.5">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setEditing(true);
              }}
              className={menuItemClass}
            >
              <Settings2 className="h-4 w-4" />
              编辑资料
            </button>
            <Link href="/dashboard" onClick={() => setOpen(false)} className={menuItemClass}>
              <LayoutDashboard className="h-4 w-4" />
              进入控制台
            </Link>
            <button type="button" onClick={handleLogout} className={menuItemClass}>
              <LogOut className="h-4 w-4" />
              退出登录
            </button>
          </div>
        </div>
      )}

      <ProfileDialog open={editing} onClose={() => setEditing(false)} />
    </div>
  );
}
