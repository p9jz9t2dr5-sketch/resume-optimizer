"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/stores/authStore";
import { useResumeStore } from "@/stores/resumeStore";
import { useChatStore } from "@/stores/chatStore";
import ConfirmDialog from "@/components/ConfirmDialog";
import { FileText, MessageSquare, ArrowRight, Plus, Trash2 } from "lucide-react";
import { useToast } from "@/stores/toastStore";

type ConfirmTarget =
  | { type: "resume"; id: string; name: string }
  | { type: "session"; id: string; title: string }
  | null;

export default function DashboardPage() {
  const router = useRouter();
  const toast = useToast();
  const { user, stats, isAuthenticated, isLoading, fetchStats } = useAuthStore();
  const { resumes, fetchResumes, deleteResume } = useResumeStore();
  const { sessions, fetchSessions, deleteSession } = useChatStore();
  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login");
      return;
    }
    if (isAuthenticated) {
      fetchStats();
      fetchResumes();
      fetchSessions();
    }
  }, [isAuthenticated, isLoading]);

  const doDelete = async () => {
    if (!confirmTarget) return;
    setIsDeleting(true);
    try {
      if (confirmTarget.type === "resume") {
        await deleteResume(confirmTarget.id);
        toast.success("简历记录已删除");
      } else {
        await deleteSession(confirmTarget.id);
        toast.success("对话/面试记录已删除");
      }
      await fetchStats().catch(() => {});
    } catch {
      toast.error("删除失败，请重试");
    } finally {
      setIsDeleting(false);
      setConfirmTarget(null);
    }
  };

  if (isLoading || !isAuthenticated) {
    return (
      <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-accent-purple border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const recentSessions = sessions.slice(0, 5);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Welcome */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold">你好，{user?.email?.split("@")[0] || "用户"}</h1>
        <p className="text-text-secondary text-sm mt-1">欢迎回到你的求职控制面板</p>
      </div>

      {/* Stats Cards */}
      <div className="grid sm:grid-cols-2 gap-4 mb-8">
        {[
          { icon: FileText, label: "简历版本", value: stats?.resume_count || 0, color: "text-accent-purple" },
          { icon: MessageSquare, label: "优化会话", value: stats?.session_count || 0, color: "text-accent-blue" },
        ].map((stat, i) => (
          <div key={i} className="glass-card p-4">
            <stat.icon className={`w-5 h-5 ${stat.color} mb-2`} />
            <p className="text-2xl font-bold">{stat.value}</p>
            <p className="text-xs text-text-muted">{stat.label}</p>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="grid lg:grid-cols-2 gap-8">
        {/* Resumes */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <FileText className="w-5 h-5 text-accent-purple" />
              我的简历
            </h2>
            <Link href="/resumes" className="text-sm text-accent-cyan hover:underline flex items-center gap-1">
              查看全部 <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          {resumes.length === 0 ? (
            <Link href="/resumes" className="glass-card p-6 text-center block hover:border-accent-purple/30 transition-all">
              <Plus className="w-8 h-8 text-text-muted mx-auto mb-2" />
              <p className="text-text-secondary text-sm">上传你的第一份简历</p>
            </Link>
          ) : (
            <div className="space-y-3">
              {resumes.slice(0, 3).map((r) => (
                <div key={r.id} className="glass-card p-3 flex items-center gap-3 group">
                  <FileText className="w-5 h-5 text-accent-cyan flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{r.original_filename}</p>
                    <p className="text-xs text-text-muted">{r.version_name} · {new Date(r.created_at).toLocaleDateString("zh-CN")}</p>
                  </div>
                  <button
                    onClick={() => setConfirmTarget({ type: "resume", id: r.id, name: r.original_filename })}
                    className="p-2 rounded-lg text-text-muted hover:text-red-400 hover:bg-red-500/10 transition-colors flex-shrink-0"
                    title="删除这条简历记录"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Sessions */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-accent-blue" />
              最近对话
            </h2>
            <Link href="/chat" className="text-sm text-accent-cyan hover:underline flex items-center gap-1">
              查看全部 <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          {recentSessions.length === 0 ? (
            <Link href="/" className="glass-card p-6 text-center block hover:border-accent-purple/30 transition-all">
              <Plus className="w-8 h-8 text-text-muted mx-auto mb-2" />
              <p className="text-text-secondary text-sm">开始你的第一次简历优化</p>
            </Link>
          ) : (
            <div className="space-y-3">
              {recentSessions.map((s) => (
                <div key={s.id} className="glass-card p-3 flex items-center gap-3 group">
                  <Link
                    href={`/chat/${s.id}`}
                    className="flex items-center gap-3 flex-1 min-w-0 hover:text-accent-cyan transition-colors"
                  >
                    <MessageSquare className="w-5 h-5 text-accent-blue flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{s.title}</p>
                      <p className="text-xs text-text-muted">{s.message_count} 条消息 · {new Date(s.updated_at).toLocaleDateString("zh-CN")}</p>
                    </div>
                  </Link>
                  <button
                    onClick={() => setConfirmTarget({ type: "session", id: s.id, title: s.title })}
                    className="p-2 rounded-lg text-text-muted hover:text-red-400 hover:bg-red-500/10 transition-colors flex-shrink-0"
                    title="删除这条对话/面试记录"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 删除确认弹窗 */}
      <ConfirmDialog
        open={confirmTarget !== null}
        title={confirmTarget?.type === "resume" ? "删除简历记录" : "删除对话记录"}
        message={
          confirmTarget?.type === "resume"
            ? `确定要删除简历记录「${confirmTarget.name}」吗？对应的上传文件与优化结果会一并删除，不可恢复。`
            : confirmTarget
              ? `确定要删除「${confirmTarget.title}」这条对话/面试记录吗？其中的消息会一并删除，不可恢复。`
              : ""
        }
        loading={isDeleting}
        onConfirm={doDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </div>
  );
}
