import { create } from "zustand";
import { authApi } from "@/lib/api";
import { setToken, clearTokens, getToken } from "@/lib/auth";

interface User {
  id: string;
  email: string;
  is_premium: boolean;
  created_at: string;
}

interface UserStats {
  resume_count: number;
  session_count: number;
  messages_today: number;
  daily_limit: number;
  is_premium: boolean;
}

interface AuthState {
  user: User | null;
  stats: UserStats | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  fetchUser: () => Promise<void>;
  fetchStats: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  stats: null,
  isLoading: true,
  isAuthenticated: false,

  login: async (email, password) => {
    const tokens = await authApi.login(email, password);
    setToken(tokens.access_token, tokens.refresh_token);
    set({ isAuthenticated: true });
    await get().fetchUser();
  },

  register: async (email, password) => {
    await authApi.register(email, password);
    // Auto-login after register
    await get().login(email, password);
  },

  logout: () => {
    clearTokens();
    set({ user: null, stats: null, isAuthenticated: false });
  },

  fetchUser: async () => {
    if (!getToken()) {
      set({ isLoading: false, isAuthenticated: false });
      return;
    }
    try {
      const user = await authApi.getMe();
      set({ user: user as User, isAuthenticated: true, isLoading: false });
    } catch {
      clearTokens();
      set({ isLoading: false, isAuthenticated: false });
    }
  },

  fetchStats: async () => {
    try {
      const stats = await authApi.getStats();
      set({ stats });
    } catch {
      // Silently ignore stats errors
    }
  },
}));
