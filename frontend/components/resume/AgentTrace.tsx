"use client";

/**
 * Agent 执行轨迹面板。
 *
 * Agent 与「一次性问答」最大的区别就是过程可解释：先规划，再逐步调工具查证据，
 * 失败会换方案，上下文太长会压缩。这个组件把这些事件（来自 POST /agent/optimize
 * 的 SSE）渲染成一条时间线，让用户看得见「AI 为什么给出这条建议」。
 *
 * 事件类型见 backend/app/api/agent.py 的模块文档；未知类型直接忽略，
 * 这样后端以后新增事件不会让前端报错。
 */

import { useMemo, useState } from "react";
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ListChecks,
  Loader2,
  Minimize2,
  RefreshCw,
  Wrench,
  XCircle,
  Zap,
} from "lucide-react";

export interface AgentEvent {
  type?: string;
  [key: string]: any;
}

interface AgentTraceProps {
  events: AgentEvent[];
  isRunning: boolean;
  runId?: string | null;
}

type Tone = "ok" | "error" | "info" | "muted" | "running";

interface TraceRow {
  key: string;
  tone: Tone;
  icon: typeof CheckCircle2;
  title: string;
  detail?: string;
}

const TONE_CLASS: Record<Tone, string> = {
  ok: "text-success",
  error: "text-danger",
  info: "text-accent",
  muted: "text-text-muted",
  running: "text-accent",
};

const STOP_REASON_LABEL: Record<string, string> = {
  completed: "正常完成",
  max_steps: "步数用尽后收尾",
  tool_unsupported: "模型不支持工具调用",
  error: "异常终止",
};

function formatInput(input: unknown): string | undefined {
  if (!input || typeof input !== "object") return undefined;
  const entries = Object.entries(input as Record<string, unknown>);
  if (entries.length === 0) return undefined;
  const text = entries
    .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join("  ·  ");
  return text.length > 240 ? `${text.slice(0, 240)}…` : text;
}

function buildRows(events: AgentEvent[], isRunning: boolean): TraceRow[] {
  const rows: TraceRow[] = [];

  events.forEach((event, index) => {
    const key = `${event.type ?? "event"}-${index}`;
    switch (event.type) {
      case "plan": {
        const steps: any[] = Array.isArray(event.plan) ? event.plan : [];
        rows.push({
          key,
          tone: "info",
          icon: ListChecks,
          title: `执行计划（${steps.length} 步）`,
          detail: steps
            .map((step, i) => {
              const intent = typeof step === "string" ? step : step?.intent ?? "";
              const tool = typeof step === "object" && step?.tool ? `（${step.tool}）` : "";
              return `${i + 1}. ${intent}${tool}`;
            })
            .join("\n"),
        });
        break;
      }
      case "thinking":
        rows.push({
          key,
          tone: "muted",
          icon: Activity,
          title: "模型说明",
          detail: String(event.content ?? "").slice(0, 300),
        });
        break;
      case "tool_call":
        rows.push({
          key,
          tone: "running",
          icon: Wrench,
          title: `调用工具 ${event.tool}`,
          detail: formatInput(event.input),
        });
        break;
      case "tool_result":
        rows.push({
          key,
          tone: event.ok ? "ok" : "error",
          icon: event.ok ? CheckCircle2 : XCircle,
          title: `${event.tool} ${event.ok ? "完成" : "失败"}${
            typeof event.latency_ms === "number" && event.latency_ms > 0
              ? ` · ${event.latency_ms}ms`
              : ""
          }`,
          detail: typeof event.summary === "string" ? event.summary : undefined,
        });
        break;
      case "replan":
        rows.push({
          key,
          tone: "info",
          icon: RefreshCw,
          title: "自动重规划",
          detail: event.reason,
        });
        break;
      case "compaction":
        rows.push({
          key,
          tone: "muted",
          icon: Minimize2,
          title: "压缩上下文",
          detail: `${event.messages_before} → ${event.messages_after} 条消息`,
        });
        break;
      case "fallback":
        rows.push({
          key,
          tone: "info",
          icon: Zap,
          title: "已降级为单次改写",
          detail: event.reason,
        });
        break;
      case "error":
        rows.push({
          key,
          tone: "error",
          icon: XCircle,
          title: "执行出错",
          detail: event.message,
        });
        break;
      case "done": {
        const chips: string[] = [];
        if (typeof event.steps === "number") chips.push(`${event.steps} 步`);
        if (typeof event.tool_calls === "number") chips.push(`${event.tool_calls} 次工具调用`);
        if (typeof event.duration_ms === "number") chips.push(`${(event.duration_ms / 1000).toFixed(1)}s`);
        if (typeof event.prompt_tokens === "number" && typeof event.completion_tokens === "number") {
          chips.push(`token ${event.prompt_tokens + event.completion_tokens}`);
        }
        if (Array.isArray(event.rewritten_sections) && event.rewritten_sections.length > 0) {
          chips.push(`改写版块：${event.rewritten_sections.join("、")}`);
        }
        rows.push({
          key,
          tone: event.stopped_reason === "completed" ? "ok" : "info",
          icon: CheckCircle2,
          title: `任务结束 · ${STOP_REASON_LABEL[event.stopped_reason] ?? event.stopped_reason ?? "已完成"}`,
          detail: chips.join(" · "),
        });
        break;
      }
      default:
        break;
    }
  });

  if (isRunning && rows.length > 0) {
    rows.push({
      key: "running",
      tone: "running",
      icon: Loader2,
      title: "Agent 正在执行",
    });
  }
  return rows;
}

export default function AgentTrace({ events, isRunning, runId }: AgentTraceProps) {
  const [collapsed, setCollapsed] = useState(false);
  const rows = useMemo(() => buildRows(events, isRunning), [events, isRunning]);

  if (rows.length === 0) return null;

  return (
    <div className="glass-card p-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <ListChecks className="w-4 h-4 text-accent" />
          <h3 className="text-sm font-semibold">Agent 执行轨迹</h3>
          <span className="text-xs text-text-muted">
            规划 → 工具调用 → 报告，全过程留痕
          </span>
        </div>
        <div className="flex items-center gap-3">
          {runId && (
            <span className="text-[11px] font-mono text-text-muted hidden sm:inline">
              run {runId.slice(0, 8)}
            </span>
          )}
          <button
            type="button"
            onClick={() => setCollapsed((prev) => !prev)}
            className="flex items-center gap-1 text-xs text-text-secondary hover:text-accent transition-colors"
          >
            {collapsed ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
            {collapsed ? "展开" : "收起"}
          </button>
        </div>
      </div>

      {!collapsed && (
        <ol className="mt-3 space-y-2 max-h-72 overflow-y-auto pr-1">
          {rows.map((row) => {
            const Icon = row.icon;
            const spinning = row.key === "running";
            return (
              <li key={row.key} className="flex items-start gap-2 text-xs">
                <Icon
                  className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${TONE_CLASS[row.tone]} ${
                    spinning ? "animate-spin" : ""
                  }`}
                />
                <div className="min-w-0">
                  <p className="text-text-secondary font-medium break-words">{row.title}</p>
                  {row.detail && (
                    <p className="text-text-muted whitespace-pre-wrap break-words mt-0.5">
                      {row.detail}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

/**
 * 「Agent 模式」开关：勾选走 Agent 链路（规划 + 工具调用 + 轨迹），
 * 取消勾选回到单次改写（更快、更省 token）。
 */
export function AgentModeSwitch({
  agentMode,
  onChange,
  disabled,
}: {
  agentMode: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label
      className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer select-none"
      title="Agent 模式会先规划、再调用工具查证据（更准但更慢）；关闭则是一次性生成建议。"
    >
      <input
        type="checkbox"
        checked={agentMode}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="w-4 h-4 accent-accent cursor-pointer disabled:cursor-not-allowed"
      />
      <span className="flex items-center gap-1.5">
        <ListChecks className="w-3.5 h-3.5" />
        Agent 模式
      </span>
    </label>
  );
}
