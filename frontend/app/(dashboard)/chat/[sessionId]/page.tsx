"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/stores/authStore";
import { useChatStore } from "@/stores/chatStore";
import { useResumeStore } from "@/stores/resumeStore";
import ChatBubble from "@/components/chat/ChatBubble";
import ChatInput from "@/components/chat/ChatInput";
import { ArrowLeft, FileText, Sparkles } from "lucide-react";

// 简历原文来自图片 OCR，会带 Markdown 符号（## 标题、- 列表、**加粗）。
// 简历预览要的是「干净的纯文字」——只删掉符号字符、保留全部文字，
// 而不是像 AI 对话那样渲染成标题/列表。
function stripMarkdownSymbols(text: string): string {
  if (!text) return text;
  return text
    .split("\n")
    .map((line) => {
      let t = line.replace(/^#{1,6}\s+/, "");
      t = t.replace(/^\s*[-*+]\s+/, "");
      t = t.replace(/^\s*\d+[.)]\s+/, "");
      return t;
    })
    .join("\n")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*\n]+)\*/g, "$1")
    .replace(/`([^`\n]+)`/g, "$1");
}

export default function ChatDetailPage() {
  const router = useRouter();
  const params = useParams();
  const sessionId = params?.sessionId as string;

  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const {
    currentSessionId,
    messages,
    isStreaming,
    streamingContent,
    error,
    fetchMessages,
    sendMessage,
    sessions,
  } = useChatStore();
  const { resumes, fetchResumes } = useResumeStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
      return;
    }
    if (isAuthenticated && sessionId) {
      fetchMessages(sessionId);
      // 简历数据不持久化（resumeStore 只缓存 selectedResume），刷新页面后
      // resumes 数组为空，必须主动拉取，否则左侧简历预览会"不可用"。
      fetchResumes();
    }
  }, [isAuthenticated, authLoading, sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  const session = sessions.find((s) => s.id === sessionId);
  const resume = session?.resume_id
    ? resumes.find((r) => r.id === session.resume_id)
    : null;

  const handleSend = async (content: string) => {
    await sendMessage(sessionId, content);
  };

  if (authLoading || !isAuthenticated) {
    return (
      <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-accent-purple border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Left Panel: Resume Preview */}
      <div className="hidden lg:flex flex-col w-80 border-r border-slate-700/30 bg-bg-secondary/50">
        <div className="p-4 border-b border-slate-700/30">
          <Link href="/chat" className="flex items-center gap-1.5 text-text-secondary hover:text-text-primary text-sm mb-3">
            <ArrowLeft className="w-4 h-4" />
            返回会话列表
          </Link>
          <h2 className="font-semibold text-sm flex items-center gap-2">
            <FileText className="w-4 h-4 text-accent-cyan" />
            简历预览
          </h2>
          {session?.title && (
            <p className="text-xs text-text-muted mt-1 truncate">{session.title}</p>
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {(() => {
            // 优先用脱敏版（anonymized_text）；如果为空则回退到原始 content，
            // 否则上传过的简历会因为脱敏异常/缺失而显示"不可用"。
            const resumeText = resume?.anonymized_text || resume?.content || "";
            if (!resumeText) {
              return <p className="text-sm text-text-muted text-center py-8">简历内容不可用</p>;
            }
            const isAnonymized = !!resume?.anonymized_text;
            return (
              <div>
                {isAnonymized && (
                  <div className="flex items-center gap-1.5 mb-3 text-xs text-green-400">
                    <Sparkles className="w-3.5 h-3.5" />
                    已隐藏隐私信息
                  </div>
                )}
                <div className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed">
                  {stripMarkdownSymbols(resumeText)}
                </div>
              </div>
            );
          })()}
        </div>
        {session?.jd_text && (
          <div className="p-4 border-t border-slate-700/30">
            <h3 className="text-xs font-semibold text-text-muted mb-2">目标岗位</h3>
            <p className="text-xs text-text-secondary line-clamp-4 whitespace-pre-wrap">
              {session.jd_text}
            </p>
          </div>
        )}
      </div>

      {/* Right Panel: Chat */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Chat Header (mobile) */}
        <div className="lg:hidden p-4 border-b border-slate-700/30">
          <Link href="/chat" className="flex items-center gap-1.5 text-text-secondary hover:text-text-primary text-sm mb-1">
            <ArrowLeft className="w-4 h-4" />
            返回
          </Link>
          <h2 className="font-semibold">{session?.title || "模拟面试"}</h2>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && !isStreaming && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-purple-600/20 to-blue-500/20 flex items-center justify-center mb-4">
                <Sparkles className="w-8 h-8 text-accent-purple" />
              </div>
              <h3 className="font-semibold text-lg mb-2">准备开始面试</h3>
              <p className="text-text-secondary text-sm max-w-md">
                面试官会根据你的简历，围绕项目经历和过往工作逐轮提问。
                你只需像真实面试一样，用 STAR 结构（情境-任务-行动-结果）如实回答即可。
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <ChatBubble key={msg.id} role={msg.role as "user" | "assistant"} content={msg.content} timestamp={msg.created_at} />
          ))}

          {/* Streaming indicator */}
          {isStreaming && streamingContent && (
            <ChatBubble role="assistant" content={streamingContent} isStreaming />
          )}
          {isStreaming && !streamingContent && (
            <ChatBubble role="assistant" content="" isStreaming />
          )}

          {error && (
            <div className="text-center text-red-400 text-sm py-2 bg-red-500/10 rounded-lg border border-red-500/20">
              {error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <ChatInput onSend={handleSend} isStreaming={isStreaming} />
      </div>
    </div>
  );
}
