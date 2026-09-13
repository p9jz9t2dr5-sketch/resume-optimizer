"use client";

/** 控制台侧边栏导航（宽屏显示，窄屏由导航栏折叠菜单替代）。 */

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  MessageSquare,
  Home,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "仪表盘", icon: LayoutDashboard },
  { href: "/resumes", label: "我的简历", icon: FileText },
  { href: "/chat", label: "模拟面试", icon: MessageSquare },
  { href: "/", label: "首页", icon: Home },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={`hidden md:flex flex-col sticky top-16 h-[calc(100vh-4rem)] glass border-r border-slate-700/30 transition-all duration-300 flex-shrink-0 ${
        collapsed ? "w-16" : "w-56"
      }`}
    >
      <nav className="flex-1 py-4 px-2 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all group ${
                isActive
                  ? "bg-purple-600/20 text-accent-purple border border-purple-500/20"
                  : "text-text-secondary hover:text-text-primary hover:bg-slate-700/30 border border-transparent"
              }`}
            >
              <item.icon className={`w-5 h-5 flex-shrink-0 ${isActive ? "text-accent-purple" : ""}`} />
              {!collapsed && <span>{item.label}</span>}
              {collapsed && (
                <span className="absolute left-full ml-2 px-2 py-1 bg-slate-800 text-xs text-white rounded-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
                  {item.label}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center justify-center h-10 border-t border-slate-700/30 text-text-muted hover:text-text-primary transition-colors cursor-pointer"
      >
        {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
      </button>
    </aside>
  );
}
