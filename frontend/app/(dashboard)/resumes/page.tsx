"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { useResumeStore, type Resume } from "@/stores/resumeStore";
import ResumeUploader from "@/components/resume/ResumeUploader";
import ResumeTextPreview from "@/components/resume/ResumeTextPreview";
import ConfirmDialog from "@/components/ConfirmDialog";
import { FileText, Eye, Download, Shield, Image as ImageIcon, Trash2 } from "lucide-react";
import { formatDate } from "@/lib/utils";
import { resumeApi } from "@/lib/api";
import { useToast } from "@/stores/toastStore";

function structuredSummary(parsedData: any): string | null {
  const s = parsedData?.structured;
  if (!s) return null;
  const work = Array.isArray(s.work_experience) ? s.work_experience.length : 0;
  const projects = Array.isArray(s.projects) ? s.projects.length : 0;
  const skills = Array.isArray(s.skills) ? s.skills.length : 0;
  return `工作 ${work} 段 · 项目 ${projects} 个 · 技能 ${skills} 项`;
}

type ConfirmTarget =
  | { type: "delete"; resumeId: string }
  | { type: "clear" }
  | null;

export default function ResumesPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const {
    resumes,
    fetchResumes,
    isLoading,
    selectResume,
    parseResume,
    parsingIds,
    deleteResume,
    clearResumes,
  } = useResumeStore();
  const toast = useToast();
  const [previewResume, setPreviewResume] = useState<Resume | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget>(null);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [isClearing, setIsClearing] = useState(false);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
      return;
    }
    if (isAuthenticated) fetchResumes();
  }, [isAuthenticated, authLoading]);

  const handleDelete = (id: string) => setConfirmTarget({ type: "delete", resumeId: id });
  const handleClear = () => setConfirmTarget({ type: "clear" });

  const doDelete = async () => {
    if (!confirmTarget || confirmTarget.type !== "delete") return;
    const id = confirmTarget.resumeId;
    setIsDeleting(id);
    try {
      await deleteResume(id);
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
      await clearResumes();
      toast.success("已清空所有简历");
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
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">简历管理</h1>
          <p className="text-text-secondary text-sm mt-1">上传和管理你的简历版本</p>
        </div>
      </div>

      {/* Upload Zone */}
      <div className="mb-8">
        <ResumeUploader />
      </div>

      {/* Resume List */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">简历列表 ({resumes.length})</h2>
          {resumes.length > 0 && (
            <button
              onClick={handleClear}
              disabled={isClearing}
              className="text-xs text-text-muted hover:text-red-400 flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              {isClearing ? "清空中..." : "一键清空"}
            </button>
          )}
        </div>
        {isLoading ? (
          <div className="flex justify-center py-12">
            <div className="w-8 h-8 border-2 border-accent-purple border-t-transparent rounded-full animate-spin" />
          </div>
        ) : resumes.length === 0 ? (
          <div className="glass-card p-12 text-center">
            <FileText className="w-12 h-12 text-text-muted mx-auto mb-4" />
            <p className="text-text-secondary">还没有上传简历</p>
            <p className="text-text-muted text-sm mt-1">上传你的简历开始 AI 优化</p>
          </div>
        ) : (
          <div className="space-y-4">
            {resumes.map((resume) => (
              <div
                key={resume.id}
                className="glass-card p-4 flex items-center gap-4 cursor-pointer hover:border-accent-purple/30 transition-all"
                onClick={() => setPreviewResume(resume)}
              >
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-600/20 to-blue-500/20 flex items-center justify-center flex-shrink-0">
                  <FileText className="w-5 h-5 text-accent-cyan" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{resume.original_filename}</p>
                  <div className="flex flex-wrap items-center gap-2 sm:gap-3 text-xs text-text-muted mt-0.5">
                    <span>{resume.version_name}</span>
                    <span>·</span>
                    {parsingIds.has(resume.id) ? (
                      <span className="text-accent-cyan">结构化解析中…</span>
                    ) : (
                      <span>{structuredSummary(resume.parsed_data) || `${resume.parsed_data?.word_count || 0} 词`}</span>
                    )}
                    <span>·</span>
                    <span className="flex items-center gap-1">
                      <Shield className="w-3 h-3 text-green-400" />
                      完整信息
                    </span>
                    <span>·</span>
                    <span>{formatDate(resume.created_at)}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap justify-end">
                  {!resume.parsed_data?.structured && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        parseResume(resume.id).catch(() => toast.error("结构化解析失败，请重试"));
                      }}
                      disabled={parsingIds.has(resume.id)}
                      className="text-xs px-2 py-1 rounded-lg hover:bg-slate-700/50 text-text-secondary hover:text-accent-cyan transition-colors disabled:opacity-50"
                      title="结构化解析"
                    >
                      解析
                    </button>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); setPreviewResume(resume); }}
                    className="p-2 rounded-lg hover:bg-slate-700/50 text-text-secondary hover:text-accent-cyan transition-colors"
                    title="查看内容"
                  >
                    <ImageIcon className="w-4 h-4" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      resumeApi.exportDownload(resume.id).then(() => toast.success("简历已下载")).catch(() => toast.error("下载失败，请重试"));
                    }}
                    className="p-2 rounded-lg hover:bg-slate-700/50 text-text-secondary hover:text-accent-cyan transition-colors"
                    title="下载"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); selectResume(resume); }}
                    className="p-2 rounded-lg hover:bg-slate-700/50 text-text-secondary hover:text-accent-cyan transition-colors"
                    title="设为当前"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(resume.id); }}
                    disabled={isDeleting === resume.id}
                    className="p-2 rounded-lg hover:bg-red-500/10 text-text-muted hover:text-red-400 transition-colors flex-shrink-0 disabled:opacity-50"
                    title="删除"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {previewResume && (
        <ResumeTextPreview
          title={previewResume.original_filename}
          text={previewResume.content || previewResume.anonymized_text || ""}
          onClose={() => setPreviewResume(null)}
        />
      )}

      {/* 删除/清空确认弹窗 */}
      <ConfirmDialog
        open={confirmTarget !== null}
        title={confirmTarget?.type === "clear" ? "清空所有简历" : "删除简历"}
        message={
          confirmTarget?.type === "clear"
            ? "确定要清空所有简历吗？此操作不可恢复。"
            : "确定要删除这份简历吗？删除后不可恢复。"
        }
        loading={confirmTarget?.type === "clear" ? isClearing : isDeleting !== null}
        onConfirm={confirmTarget?.type === "clear" ? doClear : doDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </div>
  );
}
