"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { useResumeStore, type Resume } from "@/stores/resumeStore";
import { useWorkbenchStore } from "@/stores/workbenchStore";
import { useChatStore } from "@/stores/chatStore";
import ResumeUploader from "@/components/resume/ResumeUploader";
import ResumeTextPreview from "@/components/resume/ResumeTextPreview";
import JDPaster from "@/components/company/JDPaster";
import MatchReport from "@/components/chat/MatchReport";
import ScoreRing from "@/components/chat/ScoreRing";
import LandingHeader from "@/components/landing/LandingHeader";
import { jdApi, resumeApi } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import { useToast } from "@/stores/toastStore";
import { Sparkles, Upload, FileSearch, MessageSquare, AlertTriangle, Wand2, Copy, Check } from "lucide-react";
import MarkdownText from "@/components/MarkdownText";

// Sample data for one-click testing (avoids needing a real file / pasting a JD)
const SAMPLE_JD = `岗位名称：AI 应用开发工程师
公司：字节跳动
部门：智能技术中心 - AI 平台部
薪资范围：25K - 40K / 月
工作地点：北京

【岗位职责】
1. 负责公司核心 AI 产品的后端架构设计与开发，包括智能客服、代码助手等产品线
2. 基于 LangChain/LlamaIndex 等框架，构建 RAG 问答系统与 Agent 智能体应用
3. 设计并优化 Prompt Engineering 策略，持续提升模型输出质量和用户体验
4. 搭建高效的知识库检索系统（向量数据库 + 混合检索），保证检索准确率和召回率
5. 开发与维护 LLM 应用的评估体系，建立自动化测试与监控报警机制
6. 与算法团队紧密协作，跟进最新 LLM 技术发展（Function Calling、Tool Use、多模态）

【岗位要求】
1. 计算机相关专业本科及以上学历，2-5 年软件开发经验
2. 精通 Python，熟悉至少一种后端框架（FastAPI / Flask / Django）
3. 熟悉 LLM 应用开发全栈技术：Prompt Engineering、RAG、Agent、向量数据库
4. 熟悉 PostgreSQL/MySQL、Redis 等数据库设计与优化
5. 了解 Docker、Kubernetes 等容器化技术，有云服务（AWS/GCP/阿里云）使用经验
6. 具备良好的系统设计能力，能独立完成从需求分析到上线交付的全流程

【加分项】
- 有大模型微调（LoRA/SFT）实战经验
- 熟悉 React/Next.js 前端开发，能独立完成全栈项目
- 有 LLM 评测框架（RAGAS、HuggingFace Evaluate）使用经验
- 开源项目贡献者或技术博客作者
- 能流利阅读英文技术文档和论文`;

const SAMPLE_RESUME = `# 张三
📱 138-0013-8000  |  ✉ zhangsan@example.com  |  📍 北京  |  GitHub: github.com/zhangsan

## 求职意向
AI 应用开发工程师（RAG / Agent 方向）

## 教育背景
**北京邮电大学** — 计算机科学与技术（本科） | 2016.09 - 2020.06
- GPA 3.7/4.0，校 ACM 程序设计竞赛二等奖

## 工作经历
**某互联网公司** — AI 应用开发工程师 | 2023.07 - 至今
- 基于 LlamaIndex 构建 Agent 智能体自动处理客服工单，人工介入率下降 35%，月均节省约 1200 人工时
- 设计 Prompt Engineering 规范并落地 LLM 评测体系（RAGAS），模型输出满意度由 78% 提升至 90%，上线故障率下降 50%
- 使用 Docker + Kubernetes 容器化部署，平稳支撑大促期间 3 倍流量，服务可用性 99.95%

**某科技公司** — 后端开发工程师 | 2020.07 - 2023.06
- 用 Python + FastAPI 将订单单体服务重构为微服务，部署效率提升 40%，稳定支撑日均 10 万+ 请求
- 基于 LangChain 搭建 RAG 知识库检索链路，检索准确率达 92%；引入 Redis 缓存热点数据，接口 P95 延迟由 320ms 降至 80ms

## 项目经历
**智能客服知识库** — 核心开发 | 2024
- 技术栈：Python / LlamaIndex / PostgreSQL + pgvector / Redis
- 负责向量检索与混合排序模块，整体召回率提升 18%

## 专业技能
- 编程语言：Python（熟练）、TypeScript（了解）
- 框架/库：FastAPI、LangChain、LlamaIndex、React
- 数据库/中间件：PostgreSQL、Redis、pgvector
- 工程化：Docker、Kubernetes、AWS

## 证书与荣誉
- AWS Certified Solutions Architect – Associate
- 公司年度技术之星（2024）

## 自我评价
5 年 Python 后端与 AI 应用开发经验，熟悉 RAG / Agent 全栈落地，擅长将业务问题拆解为可量化的技术方案并推动上线。`;

const AUTO_CYCLE_MS = 5000;

const FEATURE_TABS = [
  { key: "upload", icon: Upload, title: "上传简历", desc: "支持 PDF / Word / 图片，AI 解析后自动脱敏并保留你的真实信息。" },
  { key: "match", icon: FileSearch, title: "分析匹配", desc: "把目标岗位描述逐条比对你的经历，给出可解释的匹配度评分与改进点。" },
  { key: "optimize", icon: Wand2, title: "AI 优化", desc: "用 STAR 原则逐段改写、量化成果，把「做了什么」写成可验证的结果。" },
  { key: "interview", icon: MessageSquare, title: "模拟面试", desc: "资深面试官围绕你的项目经历逐轮追问，一次只问一个问题，答完还能让它点评。" },
] as const;

function DemoUpload() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-soft text-accent">
        <Upload className="h-7 w-7" />
      </div>
      <div className="rounded-full border border-dashed border-accent/40 bg-bg-secondary/60 px-4 py-1.5 text-xs text-text-secondary">
        点击上传 · PDF / DOCX / TXT / 图片
      </div>
      <div className="flex gap-1.5">
        {["自动脱敏", "AI 解析"].map((t) => (
          <span key={t} className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs text-accent">{t}</span>
        ))}
      </div>
    </div>
  );
}

function DemoMatch() {
  return (
    <div className="flex h-full items-center justify-center gap-8 p-6">
      <div className="relative">
        <svg width="100" height="100" className="-rotate-90">
          <circle cx="50" cy="50" r="40" fill="none" strokeWidth="6" className="text-bg-secondary" stroke="currentColor" />
          <circle cx="50" cy="50" r="40" fill="none" strokeWidth="6" stroke="#2DD4BF" strokeDasharray="251" strokeDashoffset="50" strokeLinecap="round" />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-2xl font-bold text-text-primary">80%</span>
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {["补充 TypeScript 技能", "量化团队规模", "补充 CI/CD 经历"].map((s) => (
          <div key={s} className="flex items-center gap-2 rounded-lg border border-border bg-bg-secondary/60 px-3 py-1.5 text-xs text-text-secondary">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            {s}
          </div>
        ))}
      </div>
    </div>
  );
}

function DemoOptimize() {
  return (
    <div className="flex h-full flex-col justify-center gap-3 p-6">
      <div className="flex justify-end">
        <div className="max-w-[70%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm text-accent-ink">
          帮我改得更量化一些
        </div>
      </div>
      <div className="flex justify-start">
        <div className="max-w-[80%] rounded-2xl rounded-bl-md border border-border bg-bg-secondary/60 px-4 py-2.5 text-sm text-text-secondary">
          <span className="font-medium text-accent">改写 </span>
          用 Python + FastAPI 重构订单微服务，部署效率提升 40%，稳定支撑日均 10 万+ 请求
        </div>
      </div>
      <div className="flex justify-start">
        <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-md border border-border bg-bg-secondary/60 px-4 py-3">
          <span className="h-2 w-2 rounded-full bg-accent" style={{ animation: "demo-typing-dot 1.4s infinite 0s" }} />
          <span className="h-2 w-2 rounded-full bg-accent" style={{ animation: "demo-typing-dot 1.4s infinite 0.2s" }} />
          <span className="h-2 w-2 rounded-full bg-accent" style={{ animation: "demo-typing-dot 1.4s infinite 0.4s" }} />
        </div>
      </div>
    </div>
  );
}

function FeatureDemo({ feature }: { feature: string }) {
  if (feature === "match") return <DemoMatch />;
  if (feature === "optimize") return <DemoOptimize />;
  if (feature === "interview") return <DemoInterview />;
  return <DemoUpload />;
}

function DemoInterview() {
  return (
    <div className="flex h-full flex-col justify-center gap-3 p-6">
      <div className="flex justify-start">
        <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-border bg-bg-secondary/60 px-4 py-2.5 text-sm text-text-secondary">
          <span className="font-medium text-accent">面试官 </span>
          你提到把订单接口拆成了 6 个微服务，拆分粒度是按业务边界还是按代码规模？
        </div>
      </div>
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm text-accent-ink">
          按业务边界拆的，订单创建和履约链路分开了
        </div>
      </div>
      <div className="flex justify-start">
        <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-border bg-bg-secondary/60 px-4 py-2.5 text-sm text-text-secondary">
          <span className="font-medium text-accent">面试官 </span>
          那两个服务之间的数据一致性是怎么保证的？
        </div>
      </div>
    </div>
  );
}

export default function HomePage() {
  const { selectedResume, uploadResume, refreshResume } = useResumeStore();
  const { startSession } = useChatStore();
  const {
    jdText,
    setJdText,
    jdResult,
    setJdResult,
    matchReport,
    setMatchReport,
    polishedContent,
    setPolishedContent,
  } = useWorkbenchStore();
  const router = useRouter();
  const toast = useToast();

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [isPolishing, setIsPolishing] = useState(false);
  const [polishCopied, setPolishCopied] = useState(false);
  const [previewResume, setPreviewResume] = useState<Resume | null>(null);

  // Restore persisted resume selection + workbench (JD / analysis / polish) after
  // mount. Both stores use `skipHydration` so the first client render matches the
  // server HTML, then we rehydrate from localStorage here. This is what keeps a
  // submitted resume + JD alive when the user navigates to another page and comes
  // back, or refreshes the page — no need to re-submit.
  useEffect(() => {
    useResumeStore.persist.rehydrate();
    useWorkbenchStore.persist.rehydrate();
  }, []);

  // Read JD from URL params after mount (avoids SSR hydration mismatch)
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const jd = p.get("jd");
    if (jd) {
      setJdText(decodeURIComponent(jd));
      window.history.replaceState({}, "", "/#tool");
      setTimeout(() => {
        document.getElementById("tool")?.scrollIntoView({ behavior: "smooth" });
      }, 200);
    }
  }, []);

  const handleAnalyze = async () => {
    if (!selectedResume) {
      setError("请先上传简历");
      return;
    }
    if (!jdText.trim()) {
      setError("请输入或粘贴职位描述 (JD)");
      return;
    }
    setError("");
    setIsAnalyzing(true);
    setJdResult(null);
    setMatchReport(null);
    setPolishedContent("");

    try {
      const result: any = await jdApi.parse(jdText, selectedResume.id);
      setJdResult(result);
      setMatchReport(result.match_report || null);
    } catch (e) {
      toast.error(getErrorMessage(e, "分析失败，请重试"));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleStartChat = async () => {
    if (!selectedResume || !jdText.trim()) return;
    try {
      const sessionId = await startSession(selectedResume.id, jdText);
      router.push(`/chat/${sessionId}`);
    } catch (e) {
      toast.error(getErrorMessage(e, "创建对话失败"));
    }
  };

  const handlePolish = async () => {
    if (!selectedResume || !jdText.trim()) return;
    setIsPolishing(true);
    setPolishedContent("");
    setError("");

    try {
      const stream = resumeApi.polishStream(selectedResume.id, jdText, matchReport);
      let polishedStructured: any = null;
      let _evtCount = 0;
      for await (const evt of stream) {
        _evtCount++;
        if (evt?.content) {
          setPolishedContent((prev: string) => (prev || "") + evt.content);
        }
        if (evt?.structured) {
          polishedStructured = evt.structured;
        }
      }
      console.log("[polish] done: events=", _evtCount, "structured_present=", !!polishedStructured);
      // Apply the optimized structured resume straight from the polish stream so
      // the visual preview/export reflects the changes immediately — no dependency
      // on a separate GET round-trip that could silently fail and leave the
      // preview identical to the original resume.
      // NOTE: do NOT call setPreviewResume() here — that would auto-open the
      // preview modal (showing the original resume) and hide the polished text,
      // which is not what the user expects from "一键润色".
      if (polishedStructured) {
        useResumeStore.getState().applyPolishedStructured(selectedResume.id, polishedStructured);
      }
      // Best-effort: also re-sync from the backend so a page reload keeps the
      // optimized version. Non-fatal if it fails.
      await refreshResume(selectedResume.id).catch(() => {});
    } catch (e) {
      toast.error(getErrorMessage(e, "润色失败，请重试"));
    } finally {
      setIsPolishing(false);
    }
  };

  const handleCopyPolished = () => {
    navigator.clipboard.writeText(polishedContent);
    setPolishCopied(true);
    setTimeout(() => setPolishCopied(false), 2000);
  };

  const handleLoadSampleJD = () => {
    setJdText(SAMPLE_JD);
    toast.success("已填入示例 JD");
  };

  const handleLoadSampleResume = async () => {
    const file = new File([SAMPLE_RESUME], "示例简历.txt", { type: "text/plain" });
    try {
      const result = await uploadResume(file);
      setPreviewResume(result);
      toast.success("已载入示例简历");
    } catch (e) {
      toast.error(getErrorMessage(e, "示例简历载入失败"));
    }
  };

  // Hero secondary CTA: load the sample resume, then take the user straight to
  // the workbench so "try it" actually does something.
  const handleTrySample = async () => {
    await handleLoadSampleResume();
    document.getElementById("tool")?.scrollIntoView({ behavior: "smooth" });
  };

  const [activeFeature, setActiveFeature] = useState(0);
  const [featurePaused, setFeaturePaused] = useState(false);
  const selectFeature = (i: number) => {
    setActiveFeature(i);
    setFeaturePaused(true);
    window.setTimeout(() => setFeaturePaused(false), 10000);
  };

  useEffect(() => {
    if (featurePaused) return;
    const timer = window.setInterval(
      () => setActiveFeature((prev) => (prev + 1) % FEATURE_TABS.length),
      AUTO_CYCLE_MS
    );
    return () => window.clearInterval(timer);
  }, [featurePaused]);

  const activeFeatureData = FEATURE_TABS[activeFeature];

  return (
    <div className="theme-landing min-h-screen bg-bg-primary">
      <LandingHeader />

      {/* Hero — centred copy, brand bloom, dot grid, floating resume swatches.
          Mirrors the reference landing page's composition on this project's
          existing dark-teal theme. */}
      <section className="relative overflow-hidden px-4 pt-16 pb-24 sm:px-6 lg:px-8">
        <div
          className="pointer-events-none absolute -right-40 -top-40 h-[500px] w-[500px] rounded-full opacity-20 blur-[100px]"
          style={{ background: "radial-gradient(circle, var(--accent), transparent 70%)" }}
        />
        <div
          className="pointer-events-none absolute -bottom-40 -left-40 h-[400px] w-[400px] rounded-full opacity-15 blur-[100px]"
          style={{ background: "radial-gradient(circle, #2DD4BF, transparent 70%)" }}
        />
        <div className="hero-dot-grid pointer-events-none absolute inset-0 opacity-40" />

        <div className="relative z-10 mx-auto max-w-4xl text-center">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/25 bg-accent-soft mb-6 px-4 py-1.5 text-sm font-medium text-accent">
            <Sparkles className="h-3.5 w-3.5" />
            AI 简历优化 · 模拟面试助手
          </span>

          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl lg:text-7xl">
            <span className="bg-gradient-to-r from-text-primary via-text-secondary to-accent bg-clip-text text-transparent">
              让每一段经历都对得上 JD
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-text-secondary sm:text-lg md:text-xl">
            上传简历并粘贴目标岗位描述，AI 给出匹配度评分、按 STAR 原则逐段改写，再用一场模拟面试把经历讲清楚。
          </p>

          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <a
              href="#tool"
              className="btn-gradient flex h-12 w-full items-center justify-center gap-2 px-8 text-base sm:h-11 sm:w-auto sm:text-sm"
            >
              <Sparkles className="h-4 w-4" />
              开始优化简历
            </a>
            <button
              onClick={handleTrySample}
              className="btn-ghost flex h-12 w-full items-center justify-center gap-2 px-6 text-base sm:h-11 sm:w-auto sm:text-sm"
            >
              用示例体验
            </button>
          </div>

        </div>
      </section>

      {/* Features — interactive tabbed showcase, reference style */}
      <section id="features" className="px-4 py-20 sm:py-28">
        <div className="mx-auto max-w-7xl">
          <div className="mx-auto mb-12 max-w-2xl text-center">
            <h2 className="text-2xl font-semibold tracking-tight text-text-primary sm:text-3xl">功能特色</h2>
            <p className="mt-4 text-text-secondary sm:text-lg">从上传简历到逐段优化，每一步都由 AI 辅助完成。</p>
          </div>

          <div className="-mx-4 mb-10 overflow-x-auto px-4 sm:mx-0 sm:px-0 [&::-webkit-scrollbar]:hidden" style={{ scrollbarWidth: "none" }}>
            <div className="mx-auto flex w-max items-center gap-1 rounded-full border border-border bg-bg-secondary p-1">
              {FEATURE_TABS.map((f, i) => (
                <button
                  key={f.key}
                  onClick={() => selectFeature(i)}
                  className={`flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-2 text-sm font-medium transition-all ${
                    i === activeFeature
                      ? "border border-accent/30 bg-surface text-text-primary"
                      : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  <f.icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{f.title}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="mx-auto max-w-5xl overflow-hidden rounded-2xl border border-border bg-surface">
            <div className="grid grid-cols-1 lg:grid-cols-2">
              <div className="relative h-[280px] border-b border-border bg-bg-secondary/40 lg:h-[320px] lg:border-b-0 lg:border-r">
                <FeatureDemo feature={FEATURE_TABS[activeFeature].key} />
              </div>
              <div className="flex flex-col justify-center p-8 lg:p-10">
                <div key={activeFeature} style={{ animation: "demo-slide-up 0.4s ease-out both" }}>
                  <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-accent-soft text-accent">
                    <activeFeatureData.icon className="h-5 w-5" />
                  </div>
                  <h3 className="text-xl font-semibold text-text-primary">{activeFeatureData.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-text-secondary">{activeFeatureData.desc}</p>
                </div>
              </div>
            </div>
            <div className="flex gap-1 px-6 pb-4">
              {FEATURE_TABS.map((_, i) => (
                <div key={i} className="h-1 flex-1 overflow-hidden rounded-full bg-bg-secondary">
                  <div
                    className={`h-full rounded-full bg-accent transition-all ${i < activeFeature ? "w-full" : i === activeFeature ? "w-0" : "w-0"}`}
                    style={
                      i === activeFeature && !featurePaused
                        ? { animation: `demo-progress ${AUTO_CYCLE_MS}ms linear forwards` }
                        : i === activeFeature && featurePaused
                          ? { width: "100%" }
                          : undefined
                    }
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>


      {/* Stats — reference section */}
      <section className="px-4 py-16 sm:py-24">
        <div className="mx-auto max-w-5xl">
          <p className="mb-12 text-center text-sm font-medium uppercase tracking-widest text-text-muted">为什么选择我们</p>
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-4 sm:divide-x sm:divide-border">
            {[
              { v: "3 步", l: "完成优化" },
              { v: "PDF", l: "多格式解析" },
              { v: "100%", l: "隐私脱敏" },
              { v: "STAR", l: "逐段改写" },
            ].map((s) => (
              <div key={s.l} className="flex flex-col items-center justify-center sm:px-8">
                <span className="text-4xl font-bold tracking-tight text-text-primary sm:text-5xl">{s.v}</span>
                <span className="mt-2 text-sm font-medium text-text-secondary">{s.l}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Upload + JD Section */}
      <section id="tool" className="py-10 px-4">
        <div className="max-w-6xl mx-auto">
          <div className="mx-auto mb-10 max-w-2xl text-center">
            <h2 className="text-2xl font-semibold tracking-tight text-text-primary sm:text-3xl">
              上传简历，开始匹配
            </h2>
            <p className="mt-4 text-text-secondary">上传简历并粘贴目标岗位描述，分析后即可看到匹配度与优化建议。</p>
          </div>
          <div className="grid md:grid-cols-2 gap-6">
            <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <Upload className="w-4 h-4 text-accent" />
                  上传简历
                </h2>
                <button
                  onClick={handleLoadSampleResume}
                  className="text-sm text-accent hover:underline"
                >
                  使用示例简历
                </button>
              </div>
              <ResumeUploader onPreview={setPreviewResume} />
            </div>
            <div className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <FileSearch className="w-4 h-4 text-accent" />
                  粘贴职位描述
                </h2>
                <button
                  onClick={handleLoadSampleJD}
                  className="text-sm text-accent hover:underline"
                >
                  填入示例 JD
                </button>
              </div>
              <JDPaster value={jdText} onChange={setJdText} />
            </div>
          </div>

          <div className="flex flex-col items-center mt-8 gap-4">
            {error && (
              <div className="text-danger text-sm bg-danger/10 px-4 py-2 rounded-lg border border-danger/25">
                {error}
              </div>
            )}
            <button
              onClick={handleAnalyze}
              disabled={isAnalyzing || !selectedResume || !jdText.trim()}
              className="btn-gradient flex items-center gap-2 px-8 py-3 text-base disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isAnalyzing ? (
                <>
                  <span className="w-4 h-4 border-2 border-accent-ink/30 border-t-accent-ink rounded-full animate-spin" />
                  分析中...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  开始分析匹配度
                </>
              )}
            </button>
          </div>

          {/* Results */}
          {(jdResult || matchReport) && (
            <div className="mt-8 animate-fade-in">
              {matchReport ? (
                <div className="flex flex-col lg:flex-row gap-6 items-start">
                  <div className="flex-shrink-0">
                    <ScoreRing score={matchReport.overall_score} size={160} />
                  </div>
                  <div className="flex-1 w-full min-w-0 space-y-6">
                    <MatchReport report={matchReport} />

                    {!polishedContent ? (
                      <div className="flex items-center gap-3 flex-wrap">
                        <button onClick={handleStartChat} className="btn-gradient flex items-center gap-2">
                          <MessageSquare className="w-4 h-4" />
                          开始模拟面试
                        </button>
                        <button
                          onClick={handlePolish}
                          disabled={isPolishing}
                          className="btn-ghost flex items-center gap-2"
                        >
                          {isPolishing ? (
                            <>
                              <span className="w-4 h-4 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
                              生成建议中...
                            </>
                          ) : (
                            <>
                              <Wand2 className="w-4 h-4" />
                              简历优化建议
                            </>
                          )}
                        </button>
                      </div>
                    ) : (
                      <div className="glass-card p-6">
                        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
                          <div className="flex items-center gap-2">
                            <Wand2 className="w-4 h-4 text-accent" />
                            <h3 className="text-lg font-semibold">简历优化建议</h3>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={handleStartChat}
                              className="btn-gradient flex items-center gap-1.5 text-sm py-1.5 px-3"
                            >
                              <MessageSquare className="w-4 h-4" />
                              开始模拟面试
                            </button>
                            <button
                              onClick={handleCopyPolished}
                              className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-accent transition-colors px-3 py-1.5 rounded-lg border border-border hover:border-accent"
                            >
                              {polishCopied ? <Check className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4" />}
                              {polishCopied ? "已复制" : "复制全文"}
                            </button>
                          </div>
                        </div>
                        <div className="markdown-body bg-bg-primary rounded-xl p-5 border border-border max-h-[600px] overflow-y-auto">
                          <MarkdownText text={polishedContent} />
                          {isPolishing && <span className="streaming-cursor" />}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                /* Fallback: JD parsed without AI match */
                <div className="glass-card p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <FileSearch className="w-5 h-5 text-accent" />
                    <h3 className="text-lg font-semibold">JD 解析完成</h3>
                  </div>

                  {/* AI unavailable notice */}
                  <div className="mb-4 p-3 rounded-lg bg-warning/10 border border-warning/25 text-sm text-warning flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium">AI 匹配分析不可用</p>
                      <p className="text-text-muted mt-0.5">未配置 OpenAI API Key，使用基础关键词提取。配置后可得精确匹配评分。</p>
                    </div>
                  </div>

                  {/* Parsed requirements */}
                  {jdResult?.parsed_requirements && (
                    <div className="space-y-3">
                      {jdResult.parsed_requirements.keywords?.length > 0 && (
                        <div>
                          <p className="text-sm font-medium text-text-secondary mb-1.5">提取的关键词</p>
                          <div className="flex flex-wrap gap-1.5">
                            {jdResult.parsed_requirements.keywords.map((kw: string, i: number) => (
                              <span key={i} className="px-2 py-0.5 rounded-full text-xs bg-accent-soft text-accent border border-accent/25">
                                {kw}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {!polishedContent && (
                    <div className="flex items-center gap-3 mt-6 flex-wrap">
                      <button onClick={handleStartChat} className="btn-gradient flex items-center gap-2">
                        <MessageSquare className="w-4 h-4" />
                        开始模拟面试
                      </button>
                      <button
                        onClick={handlePolish}
                        disabled={isPolishing}
                        className="btn-ghost flex items-center gap-2"
                      >
                        {isPolishing ? (
                          <>
                            <span className="w-4 h-4 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
                            生成建议中...
                          </>
                        ) : (
                          <>
                            <Wand2 className="w-4 h-4" />
                            简历优化建议
                          </>
                        )}
                      </button>
                    </div>
                  )}

                  {polishedContent && (
                    <div className="mt-6 glass-card p-6">
                      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
                        <div className="flex items-center gap-2">
                          <Wand2 className="w-4 h-4 text-accent" />
                          <h3 className="text-lg font-semibold">简历优化建议</h3>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={handleStartChat}
                            className="btn-gradient flex items-center gap-1.5 text-sm py-1.5 px-3"
                          >
                            <MessageSquare className="w-4 h-4" />
                            开始模拟面试
                          </button>
                          <button
                            onClick={handleCopyPolished}
                            className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-accent transition-colors px-3 py-1.5 rounded-lg border border-border hover:border-accent"
                          >
                            {polishCopied ? <Check className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4" />}
                            {polishCopied ? "已复制" : "复制全文"}
                          </button>
                        </div>
                      </div>
                      <div className="markdown-body bg-bg-primary rounded-xl p-5 border border-border max-h-[600px] overflow-y-auto">
                        <MarkdownText text={polishedContent} />
                        {isPolishing && <span className="streaming-cursor" />}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Final CTA — gradient band, reference style */}
      <section className="px-4 py-16 sm:py-20">
        <div
          className="mx-auto max-w-6xl overflow-hidden rounded-2xl border border-accent/20 p-10 text-center sm:p-16"
          style={{ background: "linear-gradient(135deg, rgba(45,212,191,0.14), rgba(21,30,46,0.9))" }}
        >
          <h2 className="text-2xl font-semibold tracking-tight text-text-primary sm:text-3xl">
            现在就用 AI 优化你的简历
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-text-secondary">
            上传简历、粘贴 JD，几分钟内得到匹配度评分与逐段改写建议。
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <a href="#tool" className="btn-gradient flex items-center justify-center gap-2 px-8 py-3 text-base">
              <Sparkles className="h-4 w-4" />
              免费开始优化
            </a>
            <button onClick={handleTrySample} className="btn-ghost flex items-center justify-center gap-2 px-6 py-3 text-base">
              用示例体验
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border bg-bg-secondary/40">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-8 py-12 sm:grid-cols-2 sm:py-16 lg:grid-cols-[1.5fr_1fr_1fr]">
            <div className="sm:col-span-2 lg:col-span-1">
              <div className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-accent" />
                <span className="text-lg font-bold tracking-tight text-text-primary">AI Resume Optimizer</span>
              </div>
              <p className="mt-4 max-w-xs text-sm leading-relaxed text-text-muted">
                上传简历、匹配 JD、逐段改写，让每一段经历都对得上岗位要求。
              </p>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-text-primary">产品</h3>
              <ul className="mt-4 space-y-3">
                <li><a href="#features" className="block text-sm text-text-muted transition-colors hover:text-text-primary">功能特色</a></li>
                <li><a href="#tool" className="block text-sm text-text-muted transition-colors hover:text-text-primary">立即体验</a></li>
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-text-primary">支持</h3>
              <ul className="mt-4 space-y-3">
                <li><a href="#features" className="block text-sm text-text-muted transition-colors hover:text-text-primary">匹配分析</a></li>
                <li><a href="#features" className="block text-sm text-text-muted transition-colors hover:text-text-primary">AI 优化</a></li>
              </ul>
            </div>
          </div>
          <div className="border-t border-border py-6">
            <p className="text-center text-sm text-text-muted">© {new Date().getFullYear()} AI Resume Optimizer · 保留所有权利</p>
          </div>
        </div>
      </footer>

      {previewResume && (
        <ResumeTextPreview
          title={previewResume.original_filename}
          text={previewResume.content || previewResume.anonymized_text || ""}
          onClose={() => setPreviewResume(null)}
        />
      )}
    </div>
  );
}
