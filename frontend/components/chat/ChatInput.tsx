"use client";

/** 面试输入框：回车发送；流式回复期间禁用，避免并发提问打乱上下文。 */

import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { Send, Loader2 } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string) => void;
  isStreaming: boolean;
  placeholder?: string;
}

export default function ChatInput({ onSend, isStreaming, placeholder }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [value]);

  const handleSend = () => {
    if (!value.trim() || isStreaming) return;
    onSend(value.trim());
    setValue("");
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="glass border-t border-slate-700/30 p-4">
      <div className="max-w-4xl mx-auto flex items-end gap-3">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || "输入优化请求，例如：请帮我改写工作经历部分..."}
          rows={1}
          className="glass-input flex-1 p-3 text-sm resize-none min-h-[44px] max-h-[200px]"
          disabled={isStreaming}
        />
        <button
          onClick={handleSend}
          disabled={!value.trim() || isStreaming}
          className="flex-shrink-0 w-10 h-10 rounded-xl bg-gradient-to-r from-purple-600 to-blue-500 flex items-center justify-center disabled:opacity-40 transition-all hover:shadow-lg hover:shadow-purple-500/25"
        >
          {isStreaming ? (
            <Loader2 className="w-5 h-5 text-white animate-spin" />
          ) : (
            <Send className="w-5 h-5 text-white" />
          )}
        </button>
      </div>
      <p className="text-xs text-text-muted mt-2 text-center">
        Enter 发送 · Shift+Enter 换行 · AI 建议仅供参考
      </p>
    </div>
  );
}
