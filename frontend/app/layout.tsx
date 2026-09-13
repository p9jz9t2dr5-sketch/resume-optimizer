/**
 * 根布局：注入全局样式、全局导航（GlobalHeader，首页会自行隐藏）、Toast 容器，
 * 并挂载 TanStack Query 与鉴权初始化（Providers）。
 */

import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";
import GlobalHeader from "@/components/layout/GlobalHeader";
import ToastContainer from "@/components/ui/ToastContainer";

export const metadata: Metadata = {
  title: "AI Resume Optimizer — AI 简历优化平台",
  description: "AI-powered resume optimization — match your resume to top tech company job descriptions",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-bg-primary text-text-primary">
        <Providers>
          <GlobalHeader />
          <main className="flex-1">{children}</main>
          <ToastContainer />
        </Providers>
      </body>
    </html>
  );
}
