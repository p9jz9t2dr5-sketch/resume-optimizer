"use client";

import { forwardRef } from "react";

interface ResumeTemplateProps {
  text: string;
}

// Common Chinese resume section headings (best-effort detection).
const SECTION_KEYWORDS = [
  "个人信息",
  "基本信息",
  "联系方式",
  "教育经历",
  "教育背景",
  "工作经历",
  "工作经验",
  "实习经历",
  "项目经历",
  "项目经验",
  "专业技能",
  "技能特长",
  "技术栈",
  "自我评价",
  "个人简介",
  "求职意向",
  "语言能力",
  "资格证书",
  "获奖情况",
  "荣誉奖项",
  "兴趣爱好",
];

const isSectionHeading = (line: string): boolean => {
  const t = line.trim();
  if (!t) return false;

  // Known keyword, optionally followed by a colon.
  for (const kw of SECTION_KEYWORDS) {
    if (
      t === kw ||
      t === `${kw}：` ||
      t === `${kw}:` ||
      t.startsWith(`${kw}：`) ||
      t.startsWith(`${kw}:`)
    ) {
      return true;
    }
  }

  // Very short standalone title (no punctuation, no bullet markers).
  if (t.length <= 8 && !/[，。；、,.!?！？·•\-—:：]/.test(t)) {
    return true;
  }

  return false;
};

export const ResumeTemplate = forwardRef<HTMLDivElement, ResumeTemplateProps>(
  function ResumeTemplate({ text }, ref) {
    const lines = text.split(/\r?\n/);

    return (
      <div
        ref={ref}
        style={{
          width: "800px",
          minHeight: "1131px",
          background: "#ffffff",
          color: "#1e293b",
          fontFamily:
            '-apple-system, "Segoe UI", "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif',
          padding: "56px 60px",
          boxSizing: "border-box",
        }}
      >
        {/* Header */}
        <div
          style={{
            borderBottom: "2px solid #0f172a",
            paddingBottom: "16px",
            marginBottom: "24px",
            textAlign: "center",
          }}
        >
          <h1
            style={{
              fontSize: "28px",
              fontWeight: 700,
              letterSpacing: "0.15em",
              color: "#0f172a",
              margin: 0,
            }}
          >
            个人简历
          </h1>
        </div>

        {/* Body */}
        <div style={{ fontSize: "15px", lineHeight: 1.9 }}>
          {lines.map((line, i) => {
            const t = line.trim();
            if (!t) {
              return <div key={i} style={{ height: "10px" }} />;
            }
            if (isSectionHeading(line)) {
              return (
                <h2
                  key={i}
                  style={{
                    fontSize: "17px",
                    fontWeight: 700,
                    color: "#0f172a",
                    margin: "16px 0 6px",
                    borderLeft: "4px solid #7c3aed",
                    paddingLeft: "10px",
                  }}
                >
                  {t}
                </h2>
              );
            }
            return (
              <p key={i} style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {line}
              </p>
            );
          })}
        </div>
      </div>
    );
  }
);
