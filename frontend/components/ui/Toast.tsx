"use client";

/** 单条全局提示的样式（success / error / info / warning 四种配色）。 */

import { useEffect, useState, useCallback } from "react";
import { CheckCircle, XCircle, Info, AlertTriangle, X } from "lucide-react";
import type { Toast as ToastItem } from "@/stores/toastStore";

const ICON_MAP = {
  success: CheckCircle,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
};

const COLOR_MAP = {
  success: "border-green-500/30 text-green-400 bg-green-500/10",
  error: "border-red-500/30 text-red-400 bg-red-500/10",
  info: "border-blue-500/30 text-blue-400 bg-blue-500/10",
  warning: "border-yellow-500/30 text-yellow-400 bg-yellow-500/10",
};

const PROGRESS_COLOR = {
  success: "bg-green-500",
  error: "bg-red-500",
  info: "bg-blue-500",
  warning: "bg-yellow-500",
};

export default function ToastItem({
  toast,
  onDismiss,
}: {
  toast: ToastItem;
  onDismiss: (id: string) => void;
}) {
  const [exiting, setExiting] = useState(false);
  const [progress, setProgress] = useState(100);
  const duration = 4000;
  const Icon = ICON_MAP[toast.type];

  const dismiss = useCallback(() => {
    setExiting(true);
    setTimeout(() => onDismiss(toast.id), 300);
  }, [toast.id, onDismiss]);

  useEffect(() => {
    const startTime = Date.now();
    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, 100 - (elapsed / duration) * 100);
      setProgress(remaining);
      if (remaining <= 0) {
        clearInterval(interval);
        dismiss();
      }
    }, 30);

    return () => clearInterval(interval);
  }, [dismiss]);

  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-xl border backdrop-blur-md shadow-lg max-w-sm w-full transition-all duration-300 ${
        COLOR_MAP[toast.type]
      } ${exiting ? "opacity-0 translate-x-8 scale-95" : "opacity-100 translate-x-0 scale-100"}`}
      role="alert"
    >
      <Icon className="w-5 h-5 flex-shrink-0 mt-0.5" />
      <p className="text-sm flex-1">{toast.message}</p>
      <button
        onClick={dismiss}
        className="flex-shrink-0 opacity-60 hover:opacity-100 transition-opacity cursor-pointer"
      >
        <X className="w-4 h-4" />
      </button>
      {/* Progress bar */}
      <div className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full overflow-hidden">
        <div
          className={`h-full ${PROGRESS_COLOR[toast.type]} transition-all duration-75 ease-linear`}
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}
