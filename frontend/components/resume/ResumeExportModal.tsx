"use client";

import { useRef, useState } from "react";
import { X, Image as ImageIcon, FileDown } from "lucide-react";
import { ResumeTemplate } from "./ResumeTemplate";
import { VisualResumeTemplate } from "./VisualResumeTemplate";
import { downloadPng, downloadPdf } from "@/lib/exportResume";
import { useToast } from "@/stores/toastStore";

interface ResumeExportModalProps {
  text: string;
  filename: string;
  onClose: () => void;
  /** Structured resume JSON from parsed_data.structured (preferred — enables visual template) */
  structured?: any | null;
  /** Avatar / original image URL (e.g. http://localhost:8000/uploads/xxx.jpg) */
  avatarUrl?: string | null;
  /** Display name for the header (falls back to "您的姓名" when not provided) */
  name?: string;
}

export default function ResumeExportModal({
  text,
  filename,
  onClose,
  structured,
  avatarUrl,
  name,
}: ResumeExportModalProps) {
  const nodeRef = useRef<HTMLDivElement>(null);
  const toast = useToast();
  const [busy, setBusy] = useState<"png" | "pdf" | null>(null);

  // Prefer the structured visual template when the backend produced structured data
  const useVisual = !!(structured && Object.keys(structured || {}).length > 0);

  const handlePng = async () => {
    if (!nodeRef.current) return;
    setBusy("png");
    try {
      await downloadPng(nodeRef.current, filename);
      toast.success("PNG 已下载");
    } catch {
      toast.error("导出 PNG 失败，请重试");
    } finally {
      setBusy(null);
    }
  };

  const handlePdf = async () => {
    if (!nodeRef.current) return;
    setBusy("pdf");
    try {
      await downloadPdf(nodeRef.current, filename);
      toast.success("PDF 已下载");
    } catch {
      toast.error("导出 PDF 失败，请重试");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="glass-card flex flex-col w-full max-w-4xl max-h-[90vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/30 flex-shrink-0">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <ImageIcon className="w-5 h-5 text-accent-cyan" />
            {useVisual ? "视觉简历预览" : "简历预览"}
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={handlePng}
              disabled={busy !== null}
              className="btn-ghost flex items-center gap-1.5 text-sm px-3 py-1.5 border border-slate-600/40 disabled:opacity-50"
            >
              {busy === "png" ? (
                <div className="w-4 h-4 border-2 border-slate-400/30 border-t-slate-300 rounded-full animate-spin" />
              ) : (
                <ImageIcon className="w-4 h-4" />
              )}
              下载 PNG
            </button>
            <button
              onClick={handlePdf}
              disabled={busy !== null}
              className="btn-gradient flex items-center gap-1.5 text-sm px-3 py-1.5 disabled:opacity-50"
            >
              {busy === "pdf" ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <FileDown className="w-4 h-4" />
              )}
              下载 PDF
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-slate-700/50 text-text-secondary transition-colors"
              title="关闭"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Preview */}
        <div className="flex-1 overflow-auto p-6 bg-slate-900/40">
          <div className="flex justify-center">
            {useVisual ? (
              <VisualResumeTemplate
                ref={nodeRef}
                structured={structured}
                avatarUrl={avatarUrl}
                name={name}
                polishedText={text}
              />
            ) : (
              <ResumeTemplate ref={nodeRef} text={text} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}