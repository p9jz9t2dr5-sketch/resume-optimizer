import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AgentTrace, { AgentModeSwitch } from "@/components/resume/AgentTrace";

const PLAN_EVENT = {
  type: "plan",
  plan: [
    { intent: "读简历结构", tool: "list_resume_sections" },
    { intent: "算匹配度", tool: "score_resume_match" },
  ],
};

const TOOL_OK_EVENT = {
  type: "tool_result",
  tool: "check_keywords",
  ok: true,
  summary: "关键词覆盖 1/2（50%），缺失：Kubernetes",
  latency_ms: 12,
};

const TOOL_FAIL_EVENT = {
  type: "tool_result",
  tool: "score_resume_match",
  ok: false,
  summary: "工具 score_resume_match 执行失败：TimeoutError",
  latency_ms: 0,
};

const DONE_EVENT = {
  type: "done",
  stopped_reason: "completed",
  steps: 5,
  tool_calls: 3,
  duration_ms: 4200,
  prompt_tokens: 900,
  completion_tokens: 300,
  rewritten_sections: ["工作经历"],
};

describe("AgentTrace", () => {
  it("renders the plan, each tool call and the closing summary", () => {
    render(
      <AgentTrace
        events={[PLAN_EVENT, TOOL_OK_EVENT, TOOL_FAIL_EVENT, DONE_EVENT]}
        isRunning={false}
        runId="7f3a1c22-0000-0000-0000-000000000000"
      />
    );

    expect(screen.getByText("Agent 执行轨迹")).toBeInTheDocument();
    expect(screen.getByText("执行计划（2 步）")).toBeInTheDocument();
    expect(screen.getByText(/1\. 读简历结构（list_resume_sections）/)).toBeInTheDocument();
    expect(screen.getByText(/check_keywords 完成 · 12ms/)).toBeInTheDocument();
    expect(screen.getByText(/score_resume_match 失败/)).toBeInTheDocument();
    expect(screen.getByText(/任务结束 · 正常完成/)).toBeInTheDocument();
    // 结束事件里的用量与改写版块作为一行摘要展示
    expect(screen.getByText(/5 步 · 3 次工具调用 · 4\.2s · token 1200 · 改写版块：工作经历/)).toBeInTheDocument();
  });

  it("shows a live indicator while the agent is still running", () => {
    render(<AgentTrace events={[PLAN_EVENT]} isRunning runId={null} />);
    expect(screen.getByText("Agent 正在执行")).toBeInTheDocument();
  });

  it("explains the degraded path when the model cannot call tools", () => {
    render(
      <AgentTrace
        events={[{ type: "fallback", reason: "当前模型不支持工具调用（function calling）" }]}
        isRunning={false}
      />
    );
    expect(screen.getByText("已降级为单次改写")).toBeInTheDocument();
    expect(screen.getByText(/不支持工具调用/)).toBeInTheDocument();
  });

  it("ignores event types it does not know yet", () => {
    render(<AgentTrace events={[{ type: "brand_new_event", payload: 1 }]} isRunning={false} />);
    expect(screen.queryByText("Agent 执行轨迹")).not.toBeInTheDocument();
  });

  it("can be collapsed by the user", () => {
    render(<AgentTrace events={[PLAN_EVENT]} isRunning={false} />);
    fireEvent.click(screen.getByRole("button", { name: /收起/ }));
    expect(screen.queryByText("执行计划（2 步）")).not.toBeInTheDocument();
  });
});

describe("AgentModeSwitch", () => {
  it("reflects the current mode and reports changes", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <AgentModeSwitch agentMode onChange={onChange} disabled={false} />
    );

    const checkbox = screen.getByRole("checkbox");
    expect(checkbox).toBeChecked();

    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(false);

    rerender(<AgentModeSwitch agentMode={false} onChange={onChange} disabled />);
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });
});
