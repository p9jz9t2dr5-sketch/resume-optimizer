"use client";

/** 落地页顶部导航：下滚后加毛玻璃背景；已登录时右上角换成 UserMenu（头像 + 下拉菜单）。 */

import { useState, useEffect } from "react";
import { Sparkles, Menu, X } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import UserMenu from "@/components/user/UserMenu";

const NAV = [
  { href: "#features", label: "功能特色" },
  { href: "#tool", label: "立即体验" },
];

export default function LandingHeader() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const { isAuthenticated } = useAuthStore();

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Avoid SSR/hydration mismatch: only reflect the real auth state after mount.
  const authed = mounted && isAuthenticated;
  const ctaTarget = authed ? "/dashboard" : "/login";
  const ctaLabel = authed ? "进入后台" : "立即开始";

  return (
    <header
      className={`sticky top-0 z-50 w-full border-b transition-all duration-300 ${
        scrolled
          ? "border-border bg-bg-secondary/80 backdrop-blur-lg"
          : "border-transparent bg-transparent"
      }`}
    >
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-6">
          <a href="#" className="group flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-accent" />
            <span className="text-lg font-bold tracking-tight text-text-primary">
              AI Resume Optimizer
            </span>
          </a>
          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-md px-3 py-1.5 text-sm font-medium text-text-secondary transition-colors hover:text-text-primary"
              >
                {item.label}
              </a>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          {authed ? (
            <UserMenu />
          ) : (
            <a
              href={ctaTarget}
              className="hidden cursor-pointer rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition-colors hover:bg-accent-strong sm:inline-flex"
            >
              {ctaLabel}
            </a>
          )}
          <button
            className="inline-flex items-center justify-center rounded-md p-2 text-text-secondary transition-colors hover:text-text-primary md:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "关闭菜单" : "打开菜单"}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {open && (
        <div className="space-y-1 border-t border-border bg-bg-secondary/95 px-4 py-3 backdrop-blur-xl md:hidden">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              onClick={() => setOpen(false)}
              className="block rounded-lg px-3 py-2.5 text-[15px] font-medium text-text-secondary transition-colors hover:bg-accent-soft hover:text-accent"
            >
              {item.label}
            </a>
          ))}
          <a
            href={ctaTarget}
            onClick={() => setOpen(false)}
            className="mt-2 flex items-center justify-center rounded-lg bg-accent px-3 py-2.5 text-[15px] font-semibold text-accent-ink"
          >
            {ctaLabel}
          </a>
        </div>
      )}
    </header>
  );
}
