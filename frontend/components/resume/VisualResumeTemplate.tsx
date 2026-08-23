"use client";

import { forwardRef, useState } from "react";

/**
 * VisualResumeTemplate —— 锤子简历风格的左右栏视觉模板
 *
 * 数据来源：
 *   - structured: 来自后端 parsed_data.structured（基础信息/教育/工作/项目/技能/证书）
 *   - name:       头部姓名（默认从 structured.basic_info 推断或 filename）
 *   - avatarUrl:  头像 URL（首版传原图 URL 即可）
 *   - polishedText: 可选 markdown 文本，作为长描述的补充渲染（不传则只用 structured）
 */

interface BasicInfo {
  years_of_experience?: string | null;
  job_title?: string | null;
  location?: string | null;
  phone?: string | null;
  email?: string | null;
  name?: string | null;
}

interface Structured {
  basic_info?: BasicInfo;
  summary?: string | null;
  education?: Array<{
    school?: string;
    degree?: string;
    major?: string;
    start?: string;
    end?: string;
  }>;
  work_experience?: Array<{
    company?: string;
    title?: string;
    start?: string;
    end?: string;
    description?: string;
  }>;
  projects?: Array<{
    name?: string;
    role?: string;
    description?: string;
    tech_stack?: string[];
  }>;
  skills?: string[];
  certificates?: string[];
  languages?: string[];
}

interface VisualResumeTemplateProps {
  structured?: Structured | null;
  name?: string;
  avatarUrl?: string | null;
  polishedText?: string;
}

const C = {
  primary: "#1e3a8a", // 深蓝模块标题
  accent: "#3b82f6",
  text: "#1e293b",
  textMuted: "#64748b",
  border: "#e2e8f0",
  bg: "#ffffff",
  bgAlt: "#f8fafc",
};

const SectionTitle = ({ children }: { children: React.ReactNode }) => (
  <h2
    style={{
      fontSize: "14px",
      fontWeight: 700,
      color: C.primary,
      margin: "0 0 8px",
      paddingBottom: "4px",
      borderBottom: `2px solid ${C.primary}`,
      letterSpacing: "0.1em",
    }}
  >
    {children}
  </h2>
);

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div style={{ marginBottom: "6px", fontSize: "12px", lineHeight: 1.6 }}>
    <span style={{ color: C.textMuted }}>{label}：</span>
    <span style={{ color: C.text }}>{children}</span>
  </div>
);

const Item = ({ title, meta, children }: { title: string; meta?: string; children?: React.ReactNode }) => (
  <div style={{ marginBottom: "10px" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
      <span style={{ fontWeight: 600, fontSize: "13px", color: C.text }}>{title}</span>
      {meta && <span style={{ fontSize: "11px", color: C.textMuted }}>{meta}</span>}
    </div>
    {children}
  </div>
);

const BulletList = ({ items }: { items: string[] }) => (
  <ul style={{ margin: "4px 0 0", paddingLeft: "16px", fontSize: "12px", lineHeight: 1.7, color: C.text }}>
    {items.map((it, i) => (
      <li key={i} style={{ marginBottom: "2px" }}>{it}</li>
    ))}
  </ul>
);

const SkillTags = ({ items }: { items: string[] }) => (
  <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginTop: "4px" }}>
    {items.map((s, i) => (
      <span
        key={i}
        style={{
          fontSize: "11px",
          padding: "2px 8px",
          background: C.bgAlt,
          color: C.primary,
          borderRadius: "3px",
          border: `1px solid ${C.border}`,
        }}
      >
        {s}
      </span>
    ))}
  </div>
);

export const VisualResumeTemplate = forwardRef<HTMLDivElement, VisualResumeTemplateProps>(
  function VisualResumeTemplate({ structured, name, avatarUrl, polishedText }, ref) {
    const s: Structured = structured || {};
    const basic = s.basic_info || {};
    const displayName = name || basic.name || "您的姓名";
    // Three-tier avatar fallback:
    //   1) Real image that loaded and is not blank -> <img>
    //   2) No image / blank / broken -> initials placeholder (colored circle)
    //   3) Never render an empty bordered circle.
    const [imgLoaded, setImgLoaded] = useState(false);
    const [imgBlank, setImgBlank] = useState(false);
    const [imgFailed, setImgFailed] = useState(false);
    const showRealImg = !!avatarUrl && imgLoaded && !imgBlank && !imgFailed;

    // Pick a stable color from the displayed name so different users get
    // different placeholder colors.
    const palette = ["#1e3a8a", "#0f766e", "#7c3aed", "#b45309", "#be123c", "#0369a1"];
    let hash = 0;
    for (let i = 0; i < displayName.length; i++) hash = (hash * 31 + displayName.charCodeAt(i)) >>> 0;
    const placeholderBg = palette[hash % palette.length];
    const initial = displayName.trim().slice(0, 1) || "您";

    return (
      <div
        ref={ref}
        style={{
          width: "800px",
          minHeight: "1131px",
          background: C.bg,
          color: C.text,
          fontFamily:
            '-apple-system, "Segoe UI", "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif',
          padding: "40px 48px",
          boxSizing: "border-box",
        }}
      >
        {/* Header: 姓名 + 求职意向 + 头像占位 */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 100px",
            alignItems: "center",
            gap: "20px",
            paddingBottom: "18px",
            marginBottom: "18px",
            borderBottom: `3px double ${C.primary}`,
          }}
        >
          <div>
            <h1
              style={{
                fontSize: "30px",
                fontWeight: 700,
                color: C.primary,
                margin: 0,
                letterSpacing: "0.15em",
              }}
            >
              {displayName}
            </h1>
            <p style={{ fontSize: "13px", color: C.textMuted, margin: "8px 0 0" }}>
              应聘岗位：
              <span style={{ color: C.text, fontWeight: 500 }}>
                {basic.job_title || "（待定）"}
              </span>
              {basic.years_of_experience && (
                <span style={{ marginLeft: "12px" }}>
                  工作经验：
                  <span style={{ color: C.text, fontWeight: 500 }}>{basic.years_of_experience}</span>
                </span>
              )}
            </p>
          </div>

          {/* 头像区：始终保留 100×100 的占位；要么是真实头像，要么是首字母彩色圆 */}
          <div
            style={{
              width: "90px",
              height: "90px",
              borderRadius: "50%",
              border: `2px solid ${C.primary}`,
              overflow: "hidden",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: C.bg,
              justifySelf: "end",
            }}
          >
            {avatarUrl && !imgFailed && (
              <img
                src={avatarUrl}
                alt="头像"
                crossOrigin="anonymous"
                onLoad={(e) => {
                  const img = e.currentTarget;
                  try {
                    const canvas = document.createElement("canvas");
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    const ctx = canvas.getContext("2d");
                    if (ctx && img.naturalWidth > 0) {
                      ctx.drawImage(img, 0, 0);
                      const data = ctx.getImageData(
                        0,
                        0,
                        img.naturalWidth,
                        img.naturalHeight
                      ).data;
                      let sum = 0;
                      let sumSq = 0;
                      let n = 0;
                      for (let i = 0; i < data.length; i += 4) {
                        const g =
                          0.299 * data[i] +
                          0.587 * data[i + 1] +
                          0.114 * data[i + 2];
                        sum += g;
                        sumSq += g * g;
                        n++;
                      }
                      const mean = sum / n;
                      const stddev = Math.sqrt(
                        Math.max(0, sumSq / n - mean * mean)
                      );
                      if (mean >= 235 || stddev <= 18) {
                        setImgBlank(true);
                        return;
                      }
                    }
                  } catch {
                    // CORS/tainted canvas: assume image is fine
                  }
                  setImgLoaded(true);
                }}
                onError={() => setImgFailed(true)}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  display: showRealImg ? "block" : "none",
                }}
              />
            )}
            {!showRealImg && (
              <span
                aria-hidden
                style={{
                  fontSize: "36px",
                  fontWeight: 600,
                  color: "#ffffff",
                  background: placeholderBg,
                  width: "100%",
                  height: "100%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontFamily:
                    '-apple-system, "Segoe UI", "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif',
                  letterSpacing: "0.05em",
                  userSelect: "none",
                }}
              >
                {initial}
              </span>
            )}
          </div>
        </div>

        {/* Body: 左右栏 */}
        <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: "24px" }}>
          {/* 左栏 */}
          <aside>
            {(basic.phone || basic.email || basic.location) && (
              <>
                <SectionTitle>联系方式</SectionTitle>
                {basic.phone && <Field label="手机">{basic.phone}</Field>}
                {basic.email && <Field label="邮箱">{basic.email}</Field>}
                {basic.location && <Field label="现居地">{basic.location}</Field>}
              </>
            )}

            {s.summary && (
              <>
                <SectionTitle>个人简介</SectionTitle>
                <p style={{ fontSize: "12px", lineHeight: 1.7, color: C.text, margin: 0 }}>
                  {s.summary}
                </p>
              </>
            )}

            {(s.skills && s.skills.length > 0) && (
              <>
                <SectionTitle>专业技能</SectionTitle>
                <SkillTags items={s.skills} />
              </>
            )}

            {(s.certificates && s.certificates.length > 0) && (
              <>
                <SectionTitle>证书荣誉</SectionTitle>
                <BulletList items={s.certificates} />
              </>
            )}

            {(s.languages && s.languages.length > 0) && (
              <>
                <SectionTitle>语言能力</SectionTitle>
                <BulletList items={s.languages} />
              </>
            )}
          </aside>

          {/* 右栏 */}
          <main>
            {(s.education && s.education.length > 0) && (
              <>
                <SectionTitle>教育背景</SectionTitle>
                {s.education.map((e, i) => (
                  <Item
                    key={i}
                    title={`${e.school || ""} · ${e.major || ""}`}
                    meta={[e.start, e.end].filter(Boolean).join(" — ") || undefined}
                  >
                    {e.degree && (
                      <div style={{ fontSize: "11px", color: C.textMuted, marginTop: "2px" }}>
                        {e.degree}
                      </div>
                    )}
                  </Item>
                ))}
              </>
            )}

            {(s.work_experience && s.work_experience.length > 0) && (
              <>
                <SectionTitle>工作经历</SectionTitle>
                {s.work_experience.map((w, i) => (
                  <Item
                    key={i}
                    title={`${w.company || ""} · ${w.title || ""}`}
                    meta={[w.start, w.end].filter(Boolean).join(" — ") || undefined}
                  >
                    {w.description && (
                      <p style={{ fontSize: "12px", lineHeight: 1.7, color: C.text, margin: "4px 0 0", whiteSpace: "pre-wrap" }}>
                        {w.description}
                      </p>
                    )}
                  </Item>
                ))}
              </>
            )}

            {(s.projects && s.projects.length > 0) && (
              <>
                <SectionTitle>项目经历</SectionTitle>
                {s.projects.map((p, i) => (
                  <Item
                    key={i}
                    title={`${p.name || ""}${p.role ? " · " + p.role : ""}`}
                  >
                    {p.description && (
                      <p style={{ fontSize: "12px", lineHeight: 1.7, color: C.text, margin: "4px 0 0", whiteSpace: "pre-wrap" }}>
                        {p.description}
                      </p>
                    )}
                    {p.tech_stack && p.tech_stack.length > 0 && (
                      <div style={{ marginTop: "4px", fontSize: "11px", color: C.textMuted }}>
                        技术栈：{p.tech_stack.join("、")}
                      </div>
                    )}
                  </Item>
                ))}
              </>
            )}

            {/* 兜底：如果没有结构化数据但有 polishedText，则用 polishedText 渲染 */}
            {(!s.work_experience || s.work_experience.length === 0) &&
             (!s.education || s.education.length === 0) &&
             polishedText && (
              <>
                <SectionTitle>简历内容</SectionTitle>
                <pre style={{
                  fontFamily: "inherit",
                  fontSize: "12px",
                  lineHeight: 1.7,
                  whiteSpace: "pre-wrap",
                  color: C.text,
                  margin: 0,
                }}>
                  {polishedText}
                </pre>
              </>
            )}
          </main>
        </div>
      </div>
    );
  }
);