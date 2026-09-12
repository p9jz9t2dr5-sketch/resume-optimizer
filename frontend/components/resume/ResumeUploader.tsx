"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { useResumeStore, type Resume } from "@/stores/resumeStore";
import { useToast } from "@/stores/toastStore";
import { getErrorMessage } from "@/lib/utils";
import { Upload, FileText, CheckCircle, Loader2, Eye } from "lucide-react";

interface ResumeUploaderProps {
  onPreview?: (resume: Resume) => void;
}

export default function ResumeUploader({ onPreview }: ResumeUploaderProps) {
  const { selectedResume, uploadResume, isLoading, selectResume } = useResumeStore();
  const toast = useToast();

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (!file) return;

      try {
        const result = await uploadResume(file);
        toast.success(`简历 "${result.original_filename}" 已上传并完成隐私保护处理`);
      } catch (e) {
        toast.error(getErrorMessage(e, "上传失败，请重试"));
      }
    },
    [uploadResume, toast]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
      "application/msword": [".doc"],
      "text/plain": [".txt"],
      "image/png": [".png"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/webp": [".webp"],
    },
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024, // 10MB
  });

  return (
    <div>
      <div
        {...getRootProps()}
        className={`upload-zone p-8 text-center cursor-pointer transition-all ${
          isDragActive ? "border-accent-purple bg-purple-500/5" : ""
        }`}
      >
        <input {...getInputProps()} />
        {isLoading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-10 h-10 text-accent-purple animate-spin" />
            <p className="text-text-secondary">正在解析简历并隐藏隐私信息...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-purple-600/20 to-blue-500/20 flex items-center justify-center">
              <Upload className="w-7 h-7 text-accent-cyan" />
            </div>
            <p className="text-text-secondary">
              {isDragActive ? "释放文件以上传" : "拖拽简历文件到此处，或点击选择"}
            </p>
            <p className="text-xs text-text-muted">支持 PDF、Word (.docx/.doc)、TXT，以及图片简历（PNG/JPG/WEBP，自动 AI 识别），最大 10MB</p>
            <p className="text-xs text-accent-cyan flex items-center gap-1">
              <CheckCircle className="w-3 h-3" />
              上传后自动隐藏姓名、电话、邮箱等隐私信息
            </p>
          </div>
        )}
      </div>

      {/* Selected resume info */}
      {selectedResume && (
        <div className="mt-3 glass-card p-3 flex items-center gap-3">
          <FileText className="w-5 h-5 text-accent-cyan" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{selectedResume.original_filename}</p>
            <p className="text-xs text-text-muted">
              v{selectedResume.version_name} · {new Date(selectedResume.created_at).toLocaleDateString("zh-CN")}
            </p>
          </div>
          {onPreview && (
            <button
              onClick={() => onPreview(selectedResume)}
              className="text-xs text-accent-cyan hover:underline flex items-center gap-1"
            >
              <Eye className="w-3.5 h-3.5" />
              查看内容
            </button>
          )}
          <button
            onClick={() => selectResume(null)}
            className="text-xs text-text-muted hover:text-red-400 transition-colors"
          >
            移除
          </button>
        </div>
      )}
    </div>
  );
}
