"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/stores/authStore";
import { useToast } from "@/stores/toastStore";
import { Sparkles, Mail, Lock, CheckCircle } from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuthStore();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (password !== confirmPassword) {
      toast.error("两次输入的密码不一致");
      return;
    }
    if (password.length < 6) {
      toast.error("密码长度至少 6 位");
      return;
    }

    setIsLoading(true);
    try {
      await register(email, password);
      toast.success("注册成功，欢迎加入！");
      router.push("/dashboard");
    } catch (e: any) {
      toast.error(e.message || "注册失败，请重试");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center px-4 py-12">
      <div className="absolute top-1/3 left-1/3 w-80 h-80 bg-purple-600/10 rounded-full blur-3xl" />
      <div className="absolute bottom-1/3 right-1/3 w-80 h-80 bg-cyan-500/10 rounded-full blur-3xl" />

      <div className="glass-card w-full max-w-md p-8 relative z-10">
        <div className="text-center mb-8">
          <Sparkles className="w-10 h-10 text-accent-cyan mx-auto mb-3" />
          <h1 className="text-2xl font-bold">创建账户</h1>
          <p className="text-text-secondary text-sm mt-1">开始你的 AI 简历优化之旅</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">邮箱地址</label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                className="glass-input w-full pl-10 pr-4 py-2.5 text-sm" placeholder="your@email.com" required />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">密码</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                className="glass-input w-full pl-10 pr-4 py-2.5 text-sm" placeholder="至少 6 位" required />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">确认密码</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                className="glass-input w-full pl-10 pr-4 py-2.5 text-sm" placeholder="再次输入密码" required />
            </div>
          </div>

          {/* Features */}
          <div className="glass p-3 rounded-lg space-y-1.5 text-xs text-text-secondary">
            <p className="flex items-center gap-1.5"><CheckCircle className="w-3.5 h-3.5 text-green-400" />上传即自动隐藏隐私信息</p>
            <p className="flex items-center gap-1.5"><CheckCircle className="w-3.5 h-3.5 text-green-400" />AI 模拟面试，围绕简历项目逐轮追问</p>
            <p className="flex items-center gap-1.5"><CheckCircle className="w-3.5 h-3.5 text-green-400" />STAR 原则 + 量化成果改写</p>
          </div>

          <button type="submit" disabled={isLoading}
            className="btn-gradient w-full py-3 flex items-center justify-center gap-2 disabled:opacity-50">
            {isLoading ? (
              <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />注册中...</>
            ) : "注册"}
          </button>
        </form>

        <p className="text-center text-sm text-text-secondary mt-6">
          已有账户？{" "}
          <Link href="/login" className="text-accent-cyan hover:underline font-medium">登录</Link>
        </p>
      </div>
    </div>
  );
}
