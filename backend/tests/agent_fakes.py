"""测试用的假模型与假数据。

整套测试不允许联网（``conftest.py`` 会把 ``OPENAI_API_KEY`` 置空），所以 Agent
循环必须能对着一个「脚本化」的模型跑：这个文件提供 ``FakeLLM``——按 system prompt
的类型分流返回预设结果，并记录每一次调用，用于断言「循环真的按预期调了模型」。
"""

import json

from app.services.llm_service import LLMReply, ToolCallingUnsupported


def text_reply(text: str, *, prompt_tokens: int = 10, completion_tokens: int = 5) -> LLMReply:
    """一条纯文本回复（循环据此判定任务结束）。"""
    return LLMReply(
        content=text,
        finish_reason="stop",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def tool_reply(name: str, arguments: dict, *, call_id: str | None = None, content: str = "") -> LLMReply:
    """一条工具调用回复。"""
    return LLMReply(
        content=content,
        tool_calls=[
            {
                "id": call_id or f"call_{name}",
                "name": name,
                "arguments": json.dumps(arguments, ensure_ascii=False),
            }
        ],
        finish_reason="tool_calls",
        prompt_tokens=12,
        completion_tokens=6,
    )


class FakeLLM:
    """脚本化的假模型。

    - ``replies``：``complete_with_tools`` 的返回队列，用完后一直返回 ``final_text``
    - ``plan``：规划阶段的返回
    - ``rewrite`` / ``score`` / ``compact_text``：工具与压缩阶段的返回
    - ``raise_tool_unsupported``：模拟「模型不支持 tools」，用于验证降级路径
    """

    def __init__(
        self,
        replies: list[LLMReply] | None = None,
        *,
        final_text: str = "## 最终报告\n\n优化建议正文。",
        plan: dict | None = None,
        rewrite: dict | None = None,
        score: dict | None = None,
        compact_text: str = "已完成：读结构、算匹配度；缺失关键词：Kubernetes。",
        raise_tool_unsupported: bool = False,
        planner_raises: bool = False,
        parse_resume_reply: dict | None = None,
        complete_raises: bool = False,
    ):
        self.replies = list(replies or [])
        self.final_text = final_text
        self.plan = plan if plan is not None else {
            "goal": "优化简历",
            "steps": [
                {"intent": "读简历结构", "tool": "list_resume_sections"},
                {"intent": "算匹配度", "tool": "score_resume_match"},
                {"intent": "出报告", "tool": None},
            ],
        }
        self.rewrite = rewrite
        self.score = score
        self.compact_text = compact_text
        self.raise_tool_unsupported = raise_tool_unsupported
        self.planner_raises = planner_raises
        self.parse_resume_reply = parse_resume_reply
        self.complete_raises = complete_raises

        self.tool_call_rounds: list[list[str]] = []
        self.messages_seen: list[list[dict]] = []
        self.complete_kinds: list[str] = []
        self.parse_calls: list[str] = []
        self.polish_calls = 0
        self.force_final_calls = 0

    # -------------------------------------------------- 内部

    @staticmethod
    def _classify(messages: list[dict]) -> str:
        system = str((messages[0] or {}).get("content") or "") if messages else ""
        if "任务规划器" in system:
            return "plan"
        if "上下文压缩器" in system:
            return "compact"
        if "资深 HR" in system:
            return "score"
        if "简历改写专家" in system:
            return "rewrite"
        if "禁止再调用任何工具" in json.dumps(messages, ensure_ascii=False):
            return "force_final"
        return "generic"

    # -------------------------------------------------- 模型接口

    async def complete(
        self,
        messages,
        *,
        is_premium: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ) -> LLMReply:
        kind = self._classify(messages)
        self.complete_kinds.append(kind)
        if self.complete_raises:
            raise RuntimeError("model down")
        if kind == "force_final":
            self.force_final_calls += 1
            return text_reply(self.final_text)
        if kind == "plan":
            if self.planner_raises:
                raise RuntimeError("planner exploded")
            return text_reply(json.dumps(self.plan, ensure_ascii=False))
        if kind == "compact":
            return text_reply(self.compact_text)
        if kind == "score":
            payload = self.score or {
                "overall_score": 72,
                "matched_keywords": ["Python"],
                "missing_keywords": ["Kubernetes", "RAG"],
                "skill_gaps": ["缺少检索增强相关经验"],
                "suggestions": ["补一条检索链路的量化结果"],
            }
            return text_reply(json.dumps(payload, ensure_ascii=False))
        if kind == "rewrite":
            payload = self.rewrite or {
                "rewritten": "搭建订单中心微服务，接口 P99 从 800ms 降到 210ms",
                "changes": ["量化结果前置"],
                "keywords_used": ["微服务"],
                "risk_notes": [],
            }
            return text_reply(json.dumps(payload, ensure_ascii=False))
        return text_reply(self.final_text)

    async def complete_with_tools(
        self,
        messages,
        tools,
        *,
        is_premium: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMReply:
        if self.raise_tool_unsupported:
            raise ToolCallingUnsupported("This model does not support the `tools` parameter (400 bad request)")
        self.messages_seen.append(messages)
        if self.replies:
            reply = self.replies.pop(0)
            self.tool_call_rounds.append([call.get("name") for call in reply.tool_calls])
            return reply
        self.tool_call_rounds.append([])
        return text_reply(self.final_text)

    # -------------------------------------------------- 业务方法

    async def parse_resume(self, text: str, is_premium: bool = False) -> dict:
        self.parse_calls.append(text)
        if self.parse_resume_reply is not None:
            return self.parse_resume_reply
        return {
            "basic_info": {"name": "[已隐藏]"},
            "summary": "后端开发",
            "education": [],
            "work_experience": [
                {
                    "company": "某互联网公司",
                    "title": "后端开发工程师",
                    "start": "2023.07",
                    "end": "至今",
                    "description": "搭建订单中心微服务，接口 P99 从 800ms 降到 210ms",
                }
            ],
            "projects": [],
            "skills": ["Python"],
            "certificates": [],
            "languages": [],
        }

    async def polish_stream(self, resume_text, jd_text, match_report=None, is_premium=False):
        self.polish_calls += 1
        yield "## 降级报告\n"
        yield "单次改写链路产出的建议。"


SAMPLE_RESUME = """# 张三
手机：13800000000  邮箱：zhangsan@example.com
求职意向：后端开发工程师

## 教育背景
某某大学 计算机科学与技术 本科 | 2019.09 - 2023.06

## 工作经历
某互联网公司 — 后端开发工程师 | 2023.07 - 至今
- 负责订单中心微服务拆分，接口 P99 从 800ms 降到 210ms
- 参与配额系统的 Redis 原子计数改造

## 项目经历
AI 简历优化平台 — 独立开发 | 2026.03 - 至今
- 用 FastAPI + Next.js 实现简历解析、JD 匹配与 SSE 流式改写

## 专业技能
Python、FastAPI、PostgreSQL、Redis、Docker
"""

JD_TEXT = """AI 应用开发（实习生）
职责：参与 AI Agent 相关开发，负责任务规划、工具调用、记忆管理等核心功能；
结合大语言模型特性设计 RAG 检索链路，并做效果迭代。
要求：熟悉 Python，了解 LangChain / 向量数据库 / Function Calling。
"""
