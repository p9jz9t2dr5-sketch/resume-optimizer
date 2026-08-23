"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { FileText, MessageSquare, Building2, LayoutDashboard, LogOut, Sparkles } from "lucide-react";

export default function Navbar() {
  const { user, isAuthenticated, logout } = useAuthStore();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.push("/");
  };

  return (
    <nav className="sticky top-0 z-50 glass border-b border-slate-700/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 group">
            <Sparkles className="w-6 h-6 text-accent-cyan group-hover:text-accent-purple transition-colors" />
            <span className="text-lg font-bold text-gradient">
              AI Resume Optimizer
            </span>
          </Link>

          {/* Navigation Links */}
          {isAuthenticated && (
            <div className="hidden md:flex items-center gap-6">
              <Link
                href="/dashboard"
                className="flex items-center gap-1.5 text-text-secondary hover:text-text-primary transition-colors text-sm font-medium"
              >
                <LayoutDashboard className="w-4 h-4" />
                控制面板
              </Link>
              <Link
                href="/resumes"
                className="flex items-center gap-1.5 text-text-secondary hover:text-text-primary transition-colors text-sm font-medium"
              >
                <FileText className="w-4 h-4" />
                简历管理
              </Link>
              <Link
                href="/companies"
                className="flex items-center gap-1.5 text-text-secondary hover:text-text-primary transition-colors text-sm font-medium"
              >
                <Building2 className="w-4 h-4" />
                公司库
              </Link>
              <Link
                href="/chat"
                className="flex items-center gap-1.5 text-text-secondary hover:text-text-primary transition-colors text-sm font-medium"
              >
                <MessageSquare className="w-4 h-4" />
                AI 对话
              </Link>
            </div>
          )}

          {/* Right: Auth */}
          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <div className="flex items-center gap-4">
                <span className="text-sm text-text-secondary hidden sm:block">
                  {user?.email}
                </span>
                <button
                  onClick={handleLogout}
                  className="btn-ghost flex items-center gap-1.5 text-sm py-2 px-3"
                >
                  <LogOut className="w-4 h-4" />
                  <span className="hidden sm:inline">退出</span>
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Link href="/login" className="btn-ghost text-sm py-2 px-4">
                  登录
                </Link>
                <Link href="/register" className="btn-gradient text-sm py-2 px-4">
                  注册
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
