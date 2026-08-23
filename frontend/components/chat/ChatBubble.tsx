"use client";

import { Bot, User } from "lucide-react";
import { formatDate } from "@/lib/utils";
import MarkdownText from "@/components/MarkdownText";

interface ChatBubbleProps {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
  isStreaming?: boolean;
}

export default function ChatBubble({ role, content, timestamp, isStreaming }: ChatBubbleProps) {
  const isUser = role === "user";
  const isStreamingClass = isStreaming ? "streaming-cursor" : "";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""} animate-fade-in`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
          isUser
            ? "bg-gradient-to-br from-purple-600 to-blue-500"
            : "bg-gradient-to-br from-cyan-500/20 to-purple-500/20"
        }`}
      >
        {isUser ? (
          <User className="w-4 h-4 text-white" />
        ) : (
          <Bot className="w-4 h-4 text-accent-cyan" />
        )}
      </div>

      {/* Bubble */}
      <div className={`max-w-[80%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "bg-gradient-to-r from-purple-600/30 to-blue-500/30 rounded-2xl rounded-tr-md text-text-primary whitespace-pre-wrap"
              : "ai-border rounded-2xl rounded-tl-md text-text-primary"
          } ${isStreamingClass}`}
        >
          {isUser ? (
            content || "..."
          ) : content ? (
            <div className="markdown-body">
              <MarkdownText text={content} />
            </div>
          ) : isStreaming ? (
            ""
          ) : (
            "..."
          )}
        </div>
        {timestamp && (
          <p className={`text-xs text-text-muted mt-1 ${isUser ? "text-right" : "text-left"}`}>
            {formatDate(timestamp)}
          </p>
        )}
      </div>
    </div>
  );
}
