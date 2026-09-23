/**
 * 前端唯一的接口调用层：所有后端请求都从这里发出（页面不直接 fetch）。
 *
 * - API_BASE：构建时由 NEXT_PUBLIC_API_URL 注入。生产是相对路径 "/api"（经 nginx 反代），
 *   本地开发是 http://localhost:8000
 * - request()：自动带上 JWT；遇到 401 会用 refresh token 换一次新 token 再重试；
 *   把后端返回的 detail 文案直接抛成 Error，页面用它显示错误
 * - 下面按后端路由分组：authApi / resumeApi / jdApi / companyApi / chatApi / agentApi
 */

import { getToken, getRefreshToken, setAccessToken, clearTokens } from "./auth";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  is_premium: boolean;
  created_at: string;
}

/**
 * Stored media paths look like "./uploads/avatar_x.png" and are served by the
 * backend under /uploads, so they need API_BASE in front of them. In production
 * API_BASE is "/api", which nginx rewrites to the backend.
 */
export function mediaUrl(path?: string | null): string | null {
  if (!path) return null;
  return `${API_BASE}${path.replace(/^\./, "").replace(/\\/g, "/")}`;
}

interface RequestOptions extends RequestInit {
  skipAuth?: boolean;
}

// Single-flight refresh so concurrent 401s don't trigger multiple token refreshes.
let refreshPromise: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const rt = getRefreshToken();
    if (!rt) return null;
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      if (data?.access_token) {
        setAccessToken(data.access_token);
        return data.access_token;
      }
      return null;
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

function redirectToLogin() {
  if (typeof window !== "undefined") {
    // This module is not a component, so it has no router to push with; a full
    // location change is the intended behaviour here (it also drops the stale
    // in-memory auth state).
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/login";
  }
}

/** FastAPI reports human-readable failures in `detail`; fall back when absent. */
function errorDetail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { skipAuth, ...init } = options;
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  };

  if (!skipAuth) {
    const token = getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  // Don't set Content-Type for FormData (browser sets it with boundary)
  if (!(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const call = () =>
    fetch(`${API_BASE}${endpoint}`, { ...init, headers });

  let res = await call();

  // On 401, try to refresh the access token once, then retry the original request.
  if (res.status === 401 && !skipAuth) {
    const newToken = await tryRefresh();
    if (newToken) {
      headers["Authorization"] = `Bearer ${newToken}`;
      res = await call();
    }
    if (res.status === 401) {
      clearTokens();
      redirectToLogin();
      throw new Error("Unauthorized");
    }
  }

  if (res.status === 429) {
    throw new Error(errorDetail(await res.json().catch(() => null), "Rate limit exceeded"));
  }

  if (!res.ok) {
    throw new Error(errorDetail(await res.json().catch(() => null), `HTTP ${res.status}`));
  }

  return res.json();
}

// Auth
export const authApi = {
  register: (email: string, password: string) =>
    request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      skipAuth: true,
    }),

  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      skipAuth: true,
    }),

  getMe: () => request<UserProfile>("/auth/me"),

  updateProfile: (displayName: string) =>
    request<UserProfile>("/auth/me", {
      method: "PATCH",
      body: JSON.stringify({ display_name: displayName }),
    }),

  uploadAvatar: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<UserProfile>("/auth/me/avatar", {
      method: "POST",
      body: formData,
    });
  },

  removeAvatar: () =>
    request<UserProfile>("/auth/me/avatar", { method: "DELETE" }),

  /** Irreversible: removes the account, its data and its uploaded files. */
  deleteAccount: () =>
    request<{ deleted: boolean; files_removed: number; files_tracked: number }>(
      "/auth/me",
      { method: "DELETE" }
    ),

  getStats: () => request<{
    resume_count: number;
    session_count: number;
    messages_today: number;
    daily_limit: number;
    is_premium: boolean;
  }>("/auth/me/stats"),
};

// Resumes
export const resumeApi = {
  upload: (file: File, versionName?: string) => {
    const formData = new FormData();
    formData.append("file", file);
    if (versionName) formData.append("version_name", versionName);
    return request("/resumes/upload", {
      method: "POST",
      body: formData,
    });
  },

  list: () => request<{ resumes: any[]; total: number }>("/resumes"),

  deleteResume: (id: string) =>
    request<{ deleted: boolean }>(`/resumes/${id}`, { method: "DELETE" }),

  clearResumes: () =>
    request<{ deleted: number }>("/resumes", { method: "DELETE" }),

  get: (id: string) => request(`/resumes/${id}`),

  // Trigger LLM structured resume parsing (education/work/projects/skills)
  parse: (id: string) => request(`/resumes/${id}/parse`, { method: "POST" }),

  // Download anonymized resume as .txt file
  exportDownload: async (id: string) => {
    const token = getToken();
    const response = await fetch(`${API_BASE}/resumes/${id}/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Download failed");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "resume_optimized.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  // SSE streaming polish
  polishStream: async function* (resumeId: string, jdText: string, matchReport?: any) {
    const token = getToken();
    const response = await fetch(`${API_BASE}/resumes/${resumeId}/polish`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ jd_text: jdText, match_report: matchReport }),
    });

    if (!response.ok) {
      throw new Error(errorDetail(await response.json().catch(() => null), "Polish error"));
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No stream reader");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6).trim();
          if (data === "[DONE]") return;
          try {
            const parsed = JSON.parse(data);
            if (parsed.error) throw new Error(parsed.error);
            // Yield the whole event so callers can read both the streamed text
            // (parsed.content) and the optimized structured resume
            // (parsed.structured) emitted by the backend right before [DONE].
            yield parsed;
          } catch (e) {
            if (e instanceof SyntaxError) continue;
            throw e;
          }
        }
      }
    }
  },
};

// Agent（规划 + 工具调用 + 记忆 + 执行轨迹）
export const agentApi = {
  /**
   * 跑一次 Agent 简历优化任务（POST /agent/optimize，SSE）。
   *
   * 与 resumeApi.polishStream 的区别：这个接口先产出执行计划，再逐步调用工具
   * （查版块 / 查关键词 / 检索知识库 / 打分 / 改写），最后流式返回报告。
   * 逐帧 yield 原始事件，调用方按 type 自行消费：
   * run / plan / step / tool_call / tool_result / replan / compaction / thinking /
   * content（报告分片）/ structured（优化后的结构化简历）/ fallback / done / error。
   */
  streamOptimize: async function* (
    resumeId: string,
    jdText: string,
    matchReport?: any,
    maxSteps?: number
  ) {
    const token = getToken();
    const response = await fetch(`${API_BASE}/agent/optimize`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        resume_id: resumeId,
        jd_text: jdText,
        match_report: matchReport,
        max_steps: maxSteps,
      }),
    });

    if (!response.ok) {
      throw new Error(errorDetail(await response.json().catch(() => null), "Agent error"));
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No stream reader");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6).trim();
          if (data === "[DONE]") return;
          try {
            const parsed = JSON.parse(data);
            if (parsed.error) throw new Error(parsed.error);
            yield parsed;
          } catch (e) {
            if (e instanceof SyntaxError) continue;
            throw e;
          }
        }
      }
    }
  },

  /** 我的 Agent 执行记录（不含轨迹明细）。 */
  listRuns: (limit = 20) =>
    request<{ runs: any[]; total: number }>(`/agent/runs?limit=${limit}`),

  /** 一次任务的完整执行轨迹（规划 / 工具调用 / 压缩 / 收尾）。 */
  getRun: (runId: string) => request<any>(`/agent/runs/${runId}`),

  deleteRun: (runId: string) =>
    request<{ deleted: boolean }>(`/agent/runs/${runId}`, { method: "DELETE" }),

  /** 跨任务长期记忆（目标岗位、风格偏好、禁忌等）。 */
  listPreferences: () =>
    request<{ preferences: any[]; total: number; known_keys: Record<string, string> }>(
      "/agent/preferences"
    ),

  setPreference: (key: string, value: string) =>
    request<any>(`/agent/preferences/${key}`, {
      method: "PUT",
      body: JSON.stringify({ value }),
    }),

  deletePreference: (key: string) =>
    request<{ deleted: boolean }>(`/agent/preferences/${key}`, { method: "DELETE" }),
};

// JD
export const jdApi = {
  parse: (rawText: string, resumeId?: string) =>
    request("/jd/parse", {
      method: "POST",
      body: JSON.stringify({ raw_text: rawText, resume_id: resumeId }),
    }),
};

// Companies
export const companyApi = {
  search: (q?: string, page = 1, pageSize = 20) =>
    request(`/companies/search?q=${encodeURIComponent(q || "")}&page=${page}&page_size=${pageSize}`),

  list: (page = 1, pageSize = 20) =>
    request(`/companies?page=${page}&page_size=${pageSize}`),
};

// Chat
export const chatApi = {
  start: (resumeId: string, jdText: string, title?: string) =>
    request<{ session_id: string; title: string; status: string }>("/chat/start", {
      method: "POST",
      body: JSON.stringify({ resume_id: resumeId, jd_text: jdText, title }),
    }),

  listSessions: () =>
    request<{ sessions: any[]; total: number }>("/chat/sessions"),

  deleteSession: (sessionId: string) =>
    request<{ deleted: boolean }>(`/chat/${sessionId}`, { method: "DELETE" }),

  clearSessions: () =>
    request<{ deleted: number }>("/chat/sessions", { method: "DELETE" }),

  getMessages: (sessionId: string) =>
    request<any[]>(`/chat/${sessionId}/messages`),

  // SSE via fetch for POST support
  streamMessage: async function* (sessionId: string, content: string) {
    const token = getToken();
    const response = await fetch(`${API_BASE}/chat/${sessionId}/message`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ content }),
    });

    if (!response.ok) {
      throw new Error(errorDetail(await response.json().catch(() => null), "Stream error"));
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No stream reader");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data === "[DONE]") return;
          try {
            const parsed = JSON.parse(data);
            if (parsed.error) throw new Error(parsed.error);
            if (parsed.content) yield parsed.content;
          } catch (e) {
            if (e instanceof SyntaxError) continue;
            throw e;
          }
        }
      }
    }
  },
};
