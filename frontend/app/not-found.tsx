/**
 * 404 页面：任何未匹配到路由的地址都会渲染这里（无需单独配置 URL）。
 */

import Link from "next/link";
import { FileQuestion } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col items-center justify-center gap-4 px-4 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-soft text-accent">
        <FileQuestion className="h-7 w-7" />
      </div>
      <h1 className="text-2xl font-bold text-text-primary">页面不存在</h1>
      <p className="max-w-md text-sm leading-relaxed text-text-secondary">
        这个地址可能已经失效，或者链接输入有误。可以回到首页继续优化简历，也可以直接进控制面板看你的记录。
      </p>
      <div className="mt-2 flex flex-wrap items-center justify-center gap-3">
        <Link href="/" className="btn-gradient px-5 py-2.5 text-sm">
          回到首页
        </Link>
        <Link href="/dashboard" className="btn-ghost px-5 py-2.5 text-sm">
          进入控制面板
        </Link>
      </div>
    </div>
  );
}
