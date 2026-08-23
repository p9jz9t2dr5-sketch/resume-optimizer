"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/stores/authStore";
import { useChatStore } from "@/stores/chatStore";
import { resumeApi } from "@/lib/api";
import { useToast } from "@/stores/toastStore";
import ConfirmDialog from "@/components/ConfirmDialog";
import { MessageSquare, Plus, Clock, Upload, Loader2, Trash2 } from "lucide-react";
import { formatDate } from "@/lib/utils";

type ConfirmTarget =
  | { type: "delete"; sessionId: string }
  | { type: "clear" }
  | null;

export default function ChatListPage() {
  const router = useRouter();
  const toast = useToast();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const { sessions, fetchSessions, startSession, deleteSession, clearSessions } = useChatStore();
  const [isUploading, setIsUploading] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [isClearing, setIsClearing] = useState(false);
  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
      return;
    }
    if (isAuthenticated) fetchSessions();
  }, [isAuthenticated, authLoading]);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file
    if (!file) return;

    setIsUploading(true);
    try {
      const resume = (await resumeApi.upload(file)) as { id: string; original_filename: string };
      const sessionId = await startSession(resume.id, "", "模拟面试");
      toast.success("简历解析完成，面试官已就位");
      router.push(`/chat/${sessionId}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "上传简历失败");
      setIsUploading(false);
    }
  };

  const handleDelete = (id: string) => {
    setConfirmTarget({ type: "delete", sessionId: id });
  };

  const handleClear = () => {
    setConfirmTarget({ type: "clear" });
  };

  const doDelete = async () => {
    if (!confirmTarget || confirmTarget.type !== "delete") return;
    const id = confirmTarget.sessionId;
    setIsDeleting(id);
    try {
      await deleteSession(id);
      toast.success("已删除");
    } catch {
      toast.error("删除失败，请重试");
    } finally {
      setIsDeleting(null);
      setConfirmTarget(null);
    }
  };

  const doClear = async () => {
    setIsClearing(true);
    try {
      await clearSessions();
      toast.success("已清空所有记录");
    } catch {
      toast.error("清空失败，请重试");
    } finally {
      setIsClearing(false);
      setConfirmTarget(null);
    }
  };

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-accent-purple border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <MessageSquare className="w-6 h-6 text-accent-purple" />
          AI 模拟面试
        </h1>
        <p className="text-text-secondary text-sm mt-1">
          上传简历，AI 面试官会针对你的项目经历和过往工作一轮轮提问
        </p>
      </div>

      {/* Upload resume to start an interview */}
      <div className="glass-card p-6 mb-8">
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-600/20 to-blue-500/20 flex items-center justify-center flex-shrink-0">
            <Upload className="w-6 h-6 text-accent-purple" />
          </div>
          <div className="flex-1 text-center sm:text-left">
            <h2 className="font-semibold">开始一场模拟面试</h2>
            <p className="text-sm text-text-secondary mt-0.5">
              支持 PDF、Word、TXT、图片（JPG/PNG）格式，上传后面试官会自动开场提问
            </p>
          </div>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="btn-gradient flex items-center gap-2 whitespace-nowrap disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isUploading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                面试官准备中...
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                上传简历
              </>
            )}
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg,.webp"
          onChange={handleFileChange}
          className="hidden"
        />
      </div>

      {/* History */}
      {sessions.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <MessageSquare className="w-12 h-12 text-text-muted mx-auto mb-4" />
          <p className="text-text-secondary">还没有面试记录</p>
          <p className="text-text-muted text-sm mt-1">上传简历，开始你的第一场模拟面试</p>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-text-muted flex items-center gap-2">
              <Clock className="w-4 h-4" />
              历史面试记录
            </h2>
            <button
              onClick={handleClear}
              disabled={isClearing}
              className="text-xs text-text-muted hover:text-red-400 flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              {isClearing ? "清空中..." : "一键清空"}
            </button>
          </div>
          {sessions.map((session) => (
            <div
              key={session.id}
              className="glass-card p-4 flex items-center gap-4 hover:border-accent-purple/30 transition-all group"
            >
              <Link href={`/chat/${session.id}`} className="flex items-center gap-4 flex-1 min-w-0">
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500/20 to-blue-500/20 flex items-center justify-center flex-shrink-0">
                  <MessageSquare className="w-5 h-5 text-accent-purple group-hover:text-accent-cyan transition-colors" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate group-hover:text-accent-cyan transition-colors">
                    {session.title}
                  </p>
                  <p className="text-xs text-text-muted flex items-center gap-3 mt-0.5">
                    <span>{session.message_count} 条消息</span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {formatDate(session.updated_at)}
                    </span>
                  </p>
                </div>
              </Link>
              <span
                className={`px-2 py-0.5 text-xs rounded-full flex-shrink-0 ${
                  session.status === "active"
                    ? "bg-green-500/10 text-green-400 border border-green-500/20"
                    : "bg-slate-500/10 text-text-muted border border-slate-500/20"
                }`}
              >
                {session.status === "active" ? "进行中" : session.status}
              </span>
              <button
                onClick={() => handleDelete(session.id)}
                disabled={isDeleting === session.id}
                title="删除这条记录"
                className="p-2 rounded-lg text-text-muted hover:text-red-400 hover:bg-red-500/10 transition-colors flex-shrink-0 disabled:opacity-50"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 删除/清空确认弹窗 */}
      <ConfirmDialog
        open={confirmTarget !== null}
        title={confirmTarget?.type === "clear" ? "清空所有面试记录" : "删除面试记录"}
        message={
          confirmTarget?.type === "clear"
            ? "确定要清空所有历史面试记录吗？此操作不可恢复。"
            : "确定要删除这条面试记录吗？删除后不可恢复。"
        }
        loading={confirmTarget?.type === "clear" ? isClearing : isDeleting !== null}
        onConfirm={confirmTarget?.type === "clear" ? doClear : doDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </div>
  );
}
