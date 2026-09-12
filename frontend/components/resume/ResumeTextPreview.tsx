"use client";

import { useEffect, useState } from "react";
import { Check, Copy, X } from "lucide-react";

interface ResumeTextPreviewProps {
  title: string;
  text: string;
  onClose: () => void;
}

/**
 * Plain-text resume preview — shows the resume body verbatim, with no template,
 * no styling options and no file export.
 */
export default function ResumeTextPreview({ title, text, onClose }: ResumeTextPreviewProps) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const handleCopy = async () => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard can be unavailable (insecure context / denied permission).
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      <div className="relative flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-border bg-bg-card shadow-2xl shadow-black/20">
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3.5">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-text-primary">{title}</h3>
            <p className="text-xs text-text-muted">纯文本预览</p>
          </div>
          <div className="flex flex-shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={handleCopy}
              disabled={!text}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-text-secondary transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
            >
              {copied ? <Check className="h-4 w-4 text-success" /> : <Copy className="h-4 w-4" />}
              {copied ? "已复制" : "复制全文"}
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭"
              className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-accent-soft hover:text-text-primary"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto whitespace-pre-wrap break-words px-6 py-5 text-sm leading-relaxed text-text-secondary">
          {text || "（这份简历没有可显示的文本内容）"}
        </div>
      </div>
    </div>
  );
}
