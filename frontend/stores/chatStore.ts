import { create } from "zustand";
import { chatApi } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  tokens_used: number;
  created_at: string;
}

interface ChatSession {
  id: string;
  title: string;
  status: string;
  resume_id: string | null;
  jd_text: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

interface ChatState {
  sessions: ChatSession[];
  currentSessionId: string | null;
  messages: Message[];
  isStreaming: boolean;
  streamingContent: string;
  error: string | null;

  fetchSessions: () => Promise<void>;
  startSession: (resumeId: string, jdText: string, title?: string) => Promise<string>;
  fetchMessages: (sessionId: string) => Promise<void>;
  sendMessage: (sessionId: string, content: string) => Promise<void>;
  setCurrentSession: (sessionId: string | null) => void;
  clearError: () => void;
  deleteSession: (sessionId: string) => Promise<void>;
  clearSessions: () => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  messages: [],
  isStreaming: false,
  streamingContent: "",
  error: null,

  fetchSessions: async () => {
    try {
      const data = await chatApi.listSessions();
      set({ sessions: data.sessions as ChatSession[] });
    } catch (e) {
      set({ error: getErrorMessage(e, "加载会话失败") });
    }
  },

  startSession: async (resumeId, jdText, title) => {
    const result = await chatApi.start(resumeId, jdText, title);
    set({ currentSessionId: result.session_id, messages: [] });
    await get().fetchSessions();
    return result.session_id;
  },

  fetchMessages: async (sessionId) => {
    try {
      const messages = await chatApi.getMessages(sessionId);
      set({ messages: messages as Message[], currentSessionId: sessionId });
    } catch (e) {
      set({ error: getErrorMessage(e, "操作失败") });
    }
  },

  sendMessage: async (sessionId, content) => {
    set({ isStreaming: true, streamingContent: "", error: null });

    // Add user message optimistically
    const userMsg: Message = {
      id: `temp-${Date.now()}`,
      role: "user",
      content,
      tokens_used: 0,
      created_at: new Date().toISOString(),
    };
    set((s) => ({ messages: [...s.messages, userMsg] }));

    let fullContent = "";

    try {
      for await (const chunk of chatApi.streamMessage(sessionId, content)) {
        fullContent += chunk;
        set({ streamingContent: fullContent });
      }

      // Add assistant message
      const assistantMsg: Message = {
        id: `temp-${Date.now() + 1}`,
        role: "assistant",
        content: fullContent,
        tokens_used: fullContent.split(/\s+/).length,
        created_at: new Date().toISOString(),
      };
      set((s) => ({
        messages: [...s.messages, assistantMsg],
        isStreaming: false,
        streamingContent: "",
      }));

      // Refresh sessions to update message counts
      await get().fetchSessions();
    } catch (e) {
      set({ isStreaming: false, error: getErrorMessage(e, "发送消息失败") });
    }
  },

  setCurrentSession: (sessionId) => set({ currentSessionId: sessionId }),
  clearError: () => set({ error: null }),

  deleteSession: async (sessionId) => {
    try {
      await chatApi.deleteSession(sessionId);
      set((s) => ({ sessions: s.sessions.filter((x) => x.id !== sessionId) }));
      if (get().currentSessionId === sessionId) {
        set({ currentSessionId: null, messages: [] });
      }
    } catch (e) {
      set({ error: getErrorMessage(e, "操作失败") });
      throw e;
    }
  },

  clearSessions: async () => {
    try {
      await chatApi.clearSessions();
      set({ sessions: [], currentSessionId: null, messages: [] });
    } catch (e) {
      set({ error: getErrorMessage(e, "操作失败") });
      throw e;
    }
  },
}));
