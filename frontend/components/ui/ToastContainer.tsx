"use client";

/** 提示容器：挂在根布局右下角，负责渲染与超时移除（最多同时 5 条）。 */

import { useToastStore } from "@/stores/toastStore";
import ToastItem from "./Toast";

export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-[100] flex flex-col gap-3 pointer-events-none">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto relative">
          <ToastItem toast={toast} onDismiss={removeToast} />
        </div>
      ))}
    </div>
  );
}
