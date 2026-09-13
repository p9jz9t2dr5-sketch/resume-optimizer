/**
 * 全局提示（toast）：任何地方调用 useToast().success("...") 即可弹出一条，
 * 由 layout 里的 ToastContainer 统一渲染，最多同时显示 5 条。
 */
import { create } from "zustand";

export type ToastType = "success" | "error" | "info" | "warning";

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
  createdAt: number;
}

interface ToastState {
  toasts: Toast[]; // 当前显示中的提示
  addToast: (message: string, type?: ToastType) => void; // 新增一条（默认 info）
  removeToast: (id: string) => void; // 手动关闭或超时后移除
}

let counter = 0;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],

  addToast: (message, type = "info") => {
    const id = `toast-${++counter}-${Date.now()}`;
    const toast: Toast = { id, message, type, createdAt: Date.now() };
    set((s) => ({
      toasts: [...s.toasts.slice(-4), toast], // max 5 visible
    }));
  },

  removeToast: (id) => {
    set((s) => ({
      toasts: s.toasts.filter((t) => t.id !== id),
    }));
  },
}));

/** Convenience hook */
export function useToast() {
  const addToast = useToastStore((s) => s.addToast);
  return {
    success: (msg: string) => addToast(msg, "success"),
    error: (msg: string) => addToast(msg, "error"),
    info: (msg: string) => addToast(msg, "info"),
    warning: (msg: string) => addToast(msg, "warning"),
  };
}
