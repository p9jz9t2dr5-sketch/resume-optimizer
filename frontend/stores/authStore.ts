/**
 * 全局登录态（Zustand）。
 *
 * 只保存「当前用户 + 用量统计」以及操作方法；token 不在这里——它放在 localStorage
 * （见 lib/auth.ts），由 lib/api.ts 在每次请求时自动带上，遇到 401 会自动刷新一次。
 * 应用启动时 Providers → fetchUser() 会用本地 token 还原登录态。
 */
import { create } from "zustand";
import { authApi, type UserProfile } from "@/lib/api";
import { setToken, clearTokens, getToken } from "@/lib/auth";

interface UserStats {
  resume_count: number; // 简历数量（控制面板统计卡）
  session_count: number; // 模拟面试场次
  messages_today: number; // 今日已用消息条数
  daily_limit: number; // 每日上限（会员为 999999）
  is_premium: boolean; // 是否会员，决定配额与所用模型
}

interface AuthState {
  user: UserProfile | null; // 当前登录用户（昵称、头像、会员标记）
  stats: UserStats | null; // 上面那张统计表，进控制面板时拉取
  isLoading: boolean; // 应用启动后正在用本地 token 校验登录态
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>; // 登录：写 token 后拉取用户
  register: (email: string, password: string) => Promise<void>; // 注册成功后自动登录
  logout: () => void; // 清 token 与内存状态（不请求后端）
  fetchUser: () => Promise<void>; // 有 token 就拉 /auth/me 还原登录态
  fetchStats: () => Promise<void>; // 控制面板的统计数字
  updateProfile: (displayName: string) => Promise<void>; // 改昵称（1–8 字）
  uploadAvatar: (file: File) => Promise<void>; // 传头像，服务端裁剪成 256×256
  removeAvatar: () => Promise<void>; // 删头像，前端回退显示首字
  deleteAccount: () => Promise<void>; // 注销账号：远端清空数据后回到未登录态
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
      set({ user, isAuthenticated: true, isLoading: false });
    } catch {
      clearTokens();
      set({ isLoading: false, isAuthenticated: false });
    }
  },

  updateProfile: async (displayName) => {
    const user = await authApi.updateProfile(displayName);
    set({ user, isAuthenticated: true });
  },

  uploadAvatar: async (file) => {
    const user = await authApi.uploadAvatar(file);
    set({ user, isAuthenticated: true });
  },

  removeAvatar: async () => {
    const user = await authApi.removeAvatar();
    set({ user, isAuthenticated: true });
  },

  deleteAccount: async () => {
    await authApi.deleteAccount();
    clearTokens();
    set({ user: null, stats: null, isAuthenticated: false });
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
