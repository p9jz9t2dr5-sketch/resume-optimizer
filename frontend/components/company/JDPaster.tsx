"use client";

import { ClipboardPaste } from "lucide-react";

interface JDPasterProps {
  value: string;
  onChange: (value: string) => void;
}

export default function JDPaster({ value, onChange }: JDPasterProps) {
  const handlePasteFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      onChange(text);
    } catch {
      // Clipboard access denied
    }
  };

  return (
    <div className="relative">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="在此粘贴目标岗位的职位描述 (JD)...&#10;&#10;例如：&#10;岗位名称：高级前端开发工程师&#10;岗位要求：&#10;1. 精通 React、TypeScript&#10;2. 3年以上前端开发经验&#10;3. 熟悉性能优化和工程化..."
        className="glass-input w-full h-64 p-4 resize-y text-sm leading-relaxed font-mono"
      />
      <button
        onClick={handlePasteFromClipboard}
        className="absolute top-3 right-3 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 text-xs text-text-secondary hover:text-text-primary transition-colors"
      >
        <ClipboardPaste className="w-3.5 h-3.5" />
        从剪贴板粘贴
      </button>
      {value && (
        <p className="absolute bottom-3 right-3 text-xs text-text-muted">
          {value.length} 字符
        </p>
      )}
    </div>
  );
}
