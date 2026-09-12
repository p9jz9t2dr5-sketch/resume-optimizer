"use client";

import { useRef, useState } from "react";
import { X, Image as ImageIcon, FileDown } from "lucide-react";
import { ResumeTemplate, type ResumeTextVariant } from "./ResumeTemplate";
import { VisualResumeTemplate } from "./VisualResumeTemplate";
import { downloadPng, downloadPdf } from "@/lib/exportResume";
import { useToast } from "@/stores/toastStore";

export type ResumeTemplateStyle = ResumeTextVariant | "auto" | "two-column";

export const RESUME_TEMPLATE_OPTIONS: {
  value: ResumeTemplateStyle;
  label: string;
  hint: string;
}[] = [
  { value: "auto", label: "自动", hint: "有结构化数据时使用双栏版式，否则使用经典文本版式" },
  { value: "two-column", label: "双栏", hint: "结构化左右栏视觉版式" },
  { value: "classic", label: "经典", hint: "经典居中标题版式" },
  { value: "modern", label: "现代", hint: "深色渐变头部版式" },
  { value: "minimal", label: "极简", hint: "简洁清淡版式" },
];

interface ResumeExportModalProps {
  text: string;
  filename: string;
  onClose: () => void;
  /** Structured resume JSON from parsed_data.structured (preferred — enables two-column visual template) */
  structured?: any | null;
  /** Avatar / original image URL (e.g. http://localhost:8000/uploads/xxx.jpg) */
  avatarUrl?: string | null;
  /** Display name for the header (falls back to "您的姓名" when not provided) */
  name?: string;
  /** Template selected when the modal opens; defaults to "auto" */
  defaultTemplate?: ResumeTemplateStyle;
}

export default function ResumeExportModal({
  text,
  filename,
  onClose,
  structured,
  avatarUrl,
  name,
  defaultTemplate = "auto",
}: ResumeExportModalProps) {
  const nodeRef = useRef<HTMLDivElement>(null);
  const toast = useToast();
  const [busy, setBusy] = useState<"png" | "pdf" | null>(null);
  const hasStructured = !!(structured && Object.keys(structured || {}).length > 0);
  const initialTemplate: ResumeTemplateStyle =
    defaultTemplate === "two-column" && !hasStructured ? "auto" : defaultTemplate;
  const [template, setTemplate] = useState<ResumeTemplateStyle>(initialTemplate);

  const useVisual = hasStructured && (template === "auto" || template === "two-column");
  const textVariant: ResumeTextVariant =
    template === "modern" || template === "minimal" ? template : "classic";

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
            简历模板预览
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

        {/* Template picker */}
        <div className="flex items-center gap-2 px-5 py-3 border-b border-slate-700/30 flex-shrink-0 overflow-x-auto">
          <span className="text-xs text-text-muted flex-shrink-0">版式</span>
          {RESUME_TEMPLATE_OPTIONS.map((opt) => {
            const disabled = opt.value === "two-column" && !hasStructured;
            return (
              <button
                key={opt.value}
                type="button"
                disabled={disabled}
                title={opt.hint}
                onClick={() => setTemplate(opt.value)}
                className={`text-xs px-3 py-1.5 rounded-lg border transition-colors flex-shrink-0 disabled:opacity-35 disabled:cursor-not-allowed ${
                  template === opt.value
                    ? "border-accent-cyan text-accent-cyan bg-cyan-500/10"
                    : "border-slate-600/40 text-text-secondary hover:text-text-primary hover:border-slate-500/60"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        {!hasStructured && (
          <div className="px-5 py-2 bg-amber-500/5 border-b border-slate-700/30 text-xs text-amber-400/90">
            当前没有结构化简历数据，双栏版式暂不可用；可切换经典 / 现代 / 极简文本版式。
          </div>
        )}

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
              <ResumeTemplate ref={nodeRef} text={text} variant={textVariant} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
