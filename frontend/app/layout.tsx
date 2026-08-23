import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";
import Navbar from "@/components/layout/Navbar";
import ToastContainer from "@/components/ui/ToastContainer";

export const metadata: Metadata = {
  title: "AI Resume Optimizer — AI 简历优化平台",
  description: "AI-powered resume optimization — match your resume to top tech company job descriptions",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-bg-primary text-text-primary">
        <Providers>
          <Navbar />
          <main className="flex-1">{children}</main>
          <ToastContainer />
        </Providers>
      </body>
    </html>
  );
}
