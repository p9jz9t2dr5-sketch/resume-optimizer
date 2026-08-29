"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { useResumeStore, type Resume } from "@/stores/resumeStore";
import { useWorkbenchStore } from "@/stores/workbenchStore";
import { useChatStore } from "@/stores/chatStore";
import ResumeUploader from "@/components/resume/ResumeUploader";
import ResumeExportModal from "@/components/resume/ResumeExportModal";
import JDPaster from "@/components/company/JDPaster";
import MatchReport from "@/components/chat/MatchReport";
import ScoreRing from "@/components/chat/ScoreRing";
import { jdApi, resumeApi, API_BASE } from "@/lib/api";
import { useToast } from "@/stores/toastStore";
import { Sparkles, Upload, FileSearch, MessageSquare, Zap, ArrowRight, AlertTriangle, Wand2, Copy, Check } from "lucide-react";
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

export default function HomePage() {
  const { isAuthenticated } = useAuthStore();
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
  const abortRef = useRef<AbortController | null>(null);

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
      window.history.replaceState({}, "", "/#upload-section");
      setTimeout(() => {
        document.getElementById("upload-section")?.scrollIntoView({ behavior: "smooth" });
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
    } catch (e: any) {
      toast.error(e.message || "分析失败，请重试");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleStartChat = async () => {
    if (!selectedResume || !jdText.trim()) return;
    try {
      const sessionId = await startSession(selectedResume.id, jdText);
      router.push(`/chat/${sessionId}`);
    } catch (e: any) {
      toast.error(e.message || "创建对话失败");
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
    } catch (e: any) {
      toast.error(e.message || "润色失败，请重试");
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
    } catch (e: any) {
      toast.error(e.message || "示例简历载入失败");
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)]">
      {/* Hero Section */}
      <section className="relative pt-20 pb-16 px-4 overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-purple-600/10 rounded-full blur-3xl" />
        <div className="absolute top-20 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl" />

        <div className="max-w-4xl mx-auto text-center relative z-10">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full glass text-sm text-text-secondary mb-8">
            <Zap className="w-4 h-4 text-accent-cyan" />
            AI 驱动的简历优化助手
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold mb-6 leading-tight">
            用 AI 打造
            <br />
            <span className="text-gradient">专属你的顶级简历</span>
          </h1>

          <p className="text-lg text-text-secondary max-w-2xl mx-auto mb-10">
            上传简历，粘贴目标岗位描述，AI 将为你精准分析匹配度，
            并通过多轮对话帮你用 STAR 原则逐段优化，让你的简历脱颖而出
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 mb-16">
            <a href="#upload-section" className="btn-gradient flex items-center justify-center gap-2 text-lg px-8 py-3 w-full sm:w-auto">
              <Sparkles className="w-5 h-5" />
              开始优化简历
            </a>
            <a href="#how-it-works" className="btn-ghost flex items-center justify-center gap-2 text-lg px-6 py-3 w-full sm:w-auto">
              了解更多
              <ArrowRight className="w-5 h-5" />
            </a>
          </div>
        </div>
      </section>

      {/* How it Works */}
      <section id="how-it-works" className="py-16 px-4">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-3xl font-bold text-center mb-12">三步完成优化</h2>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { icon: Upload, title: "1. 上传简历", desc: "支持 PDF/Word/图片，AI 解析并保留你的真实信息" },
              { icon: FileSearch, title: "2. 粘贴 JD", desc: "粘贴目标岗位描述，AI 精准分析匹配度" },
              { icon: MessageSquare, title: "3. AI 优化", desc: "多轮对话引导，逐段 STAR 改写，量化成果" },
            ].map((step, i) => (
              <div key={i} className="glass-card p-6 text-center animate-fade-in" style={{ animationDelay: `${i * 150}ms` }}>
                <div className="w-14 h-14 mx-auto mb-4 rounded-xl bg-gradient-to-br from-purple-600/20 to-blue-500/20 flex items-center justify-center">
                  <step.icon className="w-7 h-7 text-accent-cyan" />
                </div>
                <h3 className="text-lg font-semibold mb-2">{step.title}</h3>
                <p className="text-sm text-text-secondary">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Upload + JD Section */}
      <section id="upload-section" className="py-8 px-4">
        <div className="max-w-6xl mx-auto">
          <div className="grid md:grid-cols-2 gap-8">
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold flex items-center gap-2">
                  <Upload className="w-5 h-5 text-accent-purple" />
                  上传简历
                </h2>
                <button
                  onClick={handleLoadSampleResume}
                  className="text-sm text-accent-cyan hover:underline"
                >
                  使用示例简历
                </button>
              </div>
              <ResumeUploader onPreview={setPreviewResume} />
            </div>
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold flex items-center gap-2">
                  <FileSearch className="w-5 h-5 text-accent-blue" />
                  粘贴职位描述
                </h2>
                <button
                  onClick={handleLoadSampleJD}
                  className="text-sm text-accent-cyan hover:underline"
                >
                  填入示例 JD
                </button>
              </div>
              <JDPaster value={jdText} onChange={setJdText} />
            </div>
          </div>

          <div className="flex flex-col items-center mt-8 gap-4">
            {error && (
              <div className="text-red-400 text-sm bg-red-500/10 px-4 py-2 rounded-lg border border-red-500/20">
                {error}
              </div>
            )}
            <button
              onClick={handleAnalyze}
              disabled={isAnalyzing || !selectedResume || !jdText.trim()}
              className="btn-gradient flex items-center gap-2 px-10 py-3 text-lg disabled:opacity-50 disabled:cursor-not-allowed animate-pulse-glow"
            >
              {isAnalyzing ? (
                <>
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  分析中...
                </>
              ) : (
                <>
                  <Sparkles className="w-5 h-5" />
                  开始分析匹配度
                </>
              )}
            </button>
          </div>

          {/* Results */}
          {(jdResult || matchReport) && (
            <div className="mt-8 animate-fade-in">
              {/* AI Match Report */}
              {matchReport ? (
                <div className="flex flex-col lg:flex-row gap-6 items-start">
                  <div className="flex-shrink-0">
                    <ScoreRing score={matchReport.overall_score} size={160} />
                  </div>
                  <div className="flex-1 w-full min-w-0 space-y-6">
                    <MatchReport report={matchReport} />

                    {/* Action buttons (or polished result) sit in the same right column */}
                    {!polishedContent ? (
                      <div className="flex items-center gap-3 flex-wrap">
                        <button onClick={handleStartChat} className="btn-gradient flex items-center gap-2">
                          <MessageSquare className="w-4 h-4" />
                          进入 AI 对话优化
                        </button>
                        <button
                          onClick={handlePolish}
                          disabled={isPolishing}
                          className="btn-ghost flex items-center gap-2 border border-purple-500/30 hover:border-purple-500/60 text-purple-300"
                        >
                          {isPolishing ? (
                            <>
                              <div className="w-4 h-4 border-2 border-purple-400/30 border-t-purple-400 rounded-full animate-spin" />
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
                            <Wand2 className="w-5 h-5 text-accent-purple" />
                            <h3 className="text-lg font-semibold">简历优化建议</h3>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={handleStartChat}
                              className="btn-gradient flex items-center gap-1.5 text-sm py-1.5 px-3"
                            >
                              <MessageSquare className="w-4 h-4" />
                              进入 AI 对话优化
                            </button>
                            <button
                              onClick={handleCopyPolished}
                              className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-accent-cyan transition-colors px-3 py-1.5 rounded-lg glass"
                            >
                              {polishCopied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                              {polishCopied ? "已复制" : "复制全文"}
                            </button>
                          </div>
                        </div>
                        <div className="markdown-body bg-slate-800/50 rounded-xl p-5 border border-slate-700/30 max-h-[600px] overflow-y-auto">
                          <MarkdownText text={polishedContent} />
                          {isPolishing && <span className="inline-block w-2 h-4 bg-purple-400 animate-pulse ml-0.5 align-text-bottom" />}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                /* Fallback: JD parsed without AI match */
                <div className="glass-card p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <FileSearch className="w-6 h-6 text-accent-cyan" />
                    <h3 className="text-lg font-semibold">JD 解析完成</h3>
                  </div>

                  {/* AI unavailable notice */}
                  <div className="mb-4 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-sm text-yellow-300 flex items-start gap-2">
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
                              <span key={i} className="px-2 py-0.5 rounded-full text-xs bg-blue-500/10 text-blue-300 border border-blue-500/20">
                                {kw}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Action buttons for the fallback (no match) case */}
                  {!polishedContent && (
                    <div className="flex items-center gap-3 mt-6 flex-wrap">
                      <button onClick={handleStartChat} className="btn-gradient flex items-center gap-2">
                        <MessageSquare className="w-4 h-4" />
                        进入 AI 对话优化
                      </button>
                      <button
                        onClick={handlePolish}
                        disabled={isPolishing}
                        className="btn-ghost flex items-center gap-2 border border-purple-500/30 hover:border-purple-500/60 text-purple-300"
                      >
                        {isPolishing ? (
                          <>
                            <div className="w-4 h-4 border-2 border-purple-400/30 border-t-purple-400 rounded-full animate-spin" />
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
                          <Wand2 className="w-5 h-5 text-accent-purple" />
                          <h3 className="text-lg font-semibold">简历优化建议</h3>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={handleStartChat}
                            className="btn-gradient flex items-center gap-1.5 text-sm py-1.5 px-3"
                          >
                            <MessageSquare className="w-4 h-4" />
                            进入 AI 对话优化
                          </button>
                          <button
                            onClick={handleCopyPolished}
                            className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-accent-cyan transition-colors px-3 py-1.5 rounded-lg glass"
                          >
                            {polishCopied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                            {polishCopied ? "已复制" : "复制全文"}
                          </button>
                        </div>
                      </div>
                      <div className="markdown-body bg-slate-800/50 rounded-xl p-5 border border-slate-700/30 max-h-[600px] overflow-y-auto">
                        <MarkdownText text={polishedContent} />
                        {isPolishing && <span className="inline-block w-2 h-4 bg-purple-400 animate-pulse ml-0.5 align-text-bottom" />}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-700/30 mt-16 py-8 px-4">
        <div className="max-w-6xl mx-auto text-center text-sm text-text-muted">
          <p>AI Resume Optimizer — 你的智能简历优化助手</p>
          <p className="mt-1">AI 一站式优化，生成可直接使用的简历</p>
        </div>
      </footer>

      {previewResume && (
        <ResumeExportModal
          text={previewResume.content || previewResume.anonymized_text || ""}
          filename={previewResume.original_filename.replace(/\.[^.]+$/, "")}
          onClose={() => setPreviewResume(null)}
          structured={previewResume.parsed_data?.structured || null}
          avatarUrl={
            previewResume.avatar_url
              ? `${API_BASE}${previewResume.avatar_url.replace(/^\./, "").replace(/\\/g, "/")}`
              : null
          }
        />
      )}
    </div>
  );
}
