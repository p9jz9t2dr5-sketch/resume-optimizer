"use client";

/**
 * 路由级错误边界：某个页面在渲染或请求中抛错时由它接管（替代 Next 默认的英文报错页），
 * 提供「重试」（重新渲染该路由）与「回到首页」两个出口，并把错误打到控制台/容器日志。
 */

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RotateCcw } from "lucide-react";

/**
 * Route-level error boundary. Without it Next renders its own unbranded error
 * screen and the user loses the ability to retry the failed render.
 */
export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surfaces in the browser console and in `docker compose logs frontend`.
    console.error("Unhandled application error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col items-center justify-center gap-4 px-4 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-danger/10 text-danger">
        <AlertTriangle className="h-7 w-7" />
      </div>
      <h1 className="text-2xl font-bold text-text-primary">这一步没能在页面里完成</h1>
      <p className="max-w-md text-sm leading-relaxed text-text-secondary">
        通常是后端或网络临时抖动。可以点重试再来一次；如果一直失败，稍后再访问，或先用其他功能。
      </p>
      <div className="mt-2 flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={reset}
          className="btn-gradient flex items-center gap-2 px-5 py-2.5 text-sm"
        >
          <RotateCcw className="h-4 w-4" />
          重试
        </button>
        <Link href="/" className="btn-ghost px-5 py-2.5 text-sm">
          回到首页
        </Link>
      </div>
    </div>
  );
}
