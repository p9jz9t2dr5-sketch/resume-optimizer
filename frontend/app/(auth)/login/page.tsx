"use client";

/**
 * 路由：/login（(auth) 是路由组，只用于归类文件，不出现在 URL 里）
 *
 * 登录表单：调用 authStore.login → POST /auth/login，成功后跳转 /dashboard。
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/stores/authStore";
import { useToast } from "@/stores/toastStore";
import { getErrorMessage } from "@/lib/utils";
import { Sparkles, Mail, Lock } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuthStore();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      await login(email, password);
      toast.success("登录成功");
      router.push("/dashboard");
    } catch (e) {
      toast.error(getErrorMessage(e, "登录失败，请检查邮箱和密码"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center px-4 py-12">
      {/* Background */}
      <div className="absolute top-1/3 left-1/3 w-80 h-80 bg-purple-600/10 rounded-full blur-3xl" />
      <div className="absolute bottom-1/3 right-1/3 w-80 h-80 bg-cyan-500/10 rounded-full blur-3xl" />

      <div className="glass-card w-full max-w-md p-8 relative z-10">
        {/* Logo */}
        <div className="text-center mb-8">
          <Sparkles className="w-10 h-10 text-accent-cyan mx-auto mb-3" />
          <h1 className="text-2xl font-bold">欢迎回来</h1>
          <p className="text-text-secondary text-sm mt-1">登录你的 AI 简历优化账户</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              邮箱地址
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="glass-input w-full pl-10 pr-4 py-2.5 text-sm"
                placeholder="your@email.com"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              密码
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="glass-input w-full pl-10 pr-4 py-2.5 text-sm"
                placeholder="••••••••"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="btn-gradient w-full py-3 flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                登录中...
              </>
            ) : (
              "登录"
            )}
          </button>
        </form>

        <p className="text-center text-sm text-text-secondary mt-6">
          还没有账户？{" "}
          <Link href="/register" className="text-accent-cyan hover:underline font-medium">
            注册
          </Link>
        </p>
      </div>
    </div>
  );
}
