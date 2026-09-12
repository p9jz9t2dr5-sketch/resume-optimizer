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
    window.location.href = "/login";
  }
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
    const detail = await res.json().catch(() => ({}));
    throw new Error((detail as any).detail || "Rate limit exceeded");
  }

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error((detail as any).detail || `HTTP ${res.status}`);
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
      const err = await response.json().catch(() => ({}));
      throw new Error((err as any).detail || "Polish error");
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
      const err = await response.json().catch(() => ({}));
      throw new Error((err as any).detail || "Stream error");
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
