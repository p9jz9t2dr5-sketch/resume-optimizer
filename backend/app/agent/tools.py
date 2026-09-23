"""Agent 的工具集：模型可以调用的「手和脚」。

设计约定：

1. **确定性优先**。「查版块、查关键词、检索知识库、读记忆」全部是纯 Python，
   不花 token、可离线测试；只有「打分」和「改写」才交给模型。一个 Agent 的
   成本和质量，很大程度上取决于有多少事不必问模型。
2. **失败也是结果**。参数错、超时、未知工具、异常，全部转成 ``ToolResult(ok=False)``
   回灌给模型，让它自己换方案；异常不允许抛穿整个 SSE 流。
3. **工具描述是 prompt**。每个 description 都写清「什么时候该调、参数是什么」，
   模型的调用正确率主要靠这个，而不是靠 system prompt 里喊「请正确调用工具」。
4. **输出有界**。所有工具结果都截断到固定长度：Agent 最常见的线上故障就是
   某个工具吐回一大坨文本把上下文吃光。
"""

import asyncio
import json
import logging
import math
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.agent.memory import KNOWN_KEYS, MemoryStore
from app.agent.prompts import MATCH_SCORING_SYSTEM_PROMPT, SECTION_REWRITE_SYSTEM_PROMPT
from app.agent.types import ToolResult
from app.agent.utils import (
    keyword_hits,
    loads_json_loose,
    split_resume_sections,
    tokenize_for_search,
    truncate,
    unsupported_numbers,
)
from app.config import get_settings
from app.schemas.jd import MatchReport

logger = logging.getLogger("uvicorn")
settings = get_settings()

_KB_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge_base.json"
_MAX_ARG_CHARS = 20000
_MAX_ARRAY_ITEMS = 50


# ---------------------------------------------------------------- 运行上下文


@dataclass
class ToolContext:
    """一次 Agent 任务的上下文：工具要用的所有外部依赖都在这里，便于测试注入。"""

    user_id: uuid.UUID
    llm: Any  # 需要 complete() / complete_with_tools()，测试里传假对象即可
    session_factory: Callable  # app.database.async_session
    is_premium: bool = False
    resume_id: uuid.UUID | None = None
    # 当前这次任务的 run id：记忆工具要用它把「本次任务」从历史记录里排除掉
    run_id: uuid.UUID | None = None
    resume_text: str = ""
    jd_text: str = ""
    match_report: dict | None = None


@dataclass
class ToolSpec:
    """一个工具的声明 + 实现。"""

    name: str
    description: str
    parameters: dict
    handler: Callable[..., Awaitable[ToolResult]]
    timeout: float = 15.0
    llm_backed: bool = False


# ---------------------------------------------------------------- 知识库检索


@dataclass
class _KBEntry:
    id: str
    title: str
    tags: list[str]
    content: str
    tokens: list[str] = field(default_factory=list)
    length: int = 0


@lru_cache(maxsize=1)
def load_knowledge_base() -> tuple[_KBEntry, ...]:
    """载入简历/求职知识库（首次调用读盘，之后走缓存）。"""
    try:
        with open(_KB_PATH, encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.error("agent: failed to load knowledge base => %s: %s", type(exc).__name__, exc)
        return ()
    entries: list[_KBEntry] = []
    for item in payload.get("entries", []):
        content = str(item.get("content", ""))
        tags = [str(t) for t in item.get("tags", [])]
        tokens = tokenize_for_search(" ".join([str(item.get("title", "")), " ".join(tags), content]))
        entries.append(
            _KBEntry(
                id=str(item.get("id", "")),
                title=str(item.get("title", "")),
                tags=tags,
                content=content,
                tokens=tokens,
                length=len(tokens) or 1,
            )
        )
    return tuple(entries)


def bm25_search(
    entries: tuple[_KBEntry, ...] | list[_KBEntry],
    query: str,
    top_k: int = 3,
    k1: float = 1.2,
    b: float = 0.75,
) -> list[tuple[float, _KBEntry]]:
    """BM25 检索。

    这里刻意不引入向量库：知识库只有几十条、且都是中文短文档，词项检索
    （中文走二元组）召回已经够用，还没有额外的模型依赖和延迟。
    真要做语义检索，替换点就是这一个函数。
    """
    entries = list(entries)
    query_tokens = set(tokenize_for_search(query))
    if not entries or not query_tokens:
        return []

    doc_count = len(entries)
    avg_length = sum(entry.length for entry in entries) / doc_count or 1.0
    document_frequency: Counter[str] = Counter()
    for entry in entries:
        for token in set(entry.tokens):
            document_frequency[token] += 1

    scored: list[tuple[float, _KBEntry]] = []
    for entry in entries:
        term_frequency = Counter(entry.tokens)
        score = 0.0
        for token in query_tokens:
            tf = term_frequency.get(token, 0)
            if not tf:
                continue
            df = document_frequency[token]
            idf = math.log(1 + (doc_count - df + 0.5) / (df + 0.5))
            denominator = tf + k1 * (1 - b + b * entry.length / avg_length)
            score += idf * (tf * (k1 + 1)) / denominator
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------- 简历版块定位


def _find_section(sections: dict[str, str], name: str) -> tuple[str | None, str]:
    """在切好的版块里找名字最接近的一个（精确 → 同义 → 包含）。"""
    if not sections or not name:
        return None, ""
    target = name.strip()
    if target in sections:
        return target, sections[target]
    lowered = target.lower()
    for key, value in sections.items():
        if key.lower() == lowered:
            return key, value
    for key, value in sections.items():
        if lowered and (lowered in key.lower() or key.lower() in lowered):
            return key, value
    return None, ""


# ---------------------------------------------------------------- 确定性工具


async def _tool_list_resume_sections(ctx: ToolContext, resume_text: str | None = None) -> ToolResult:
    """把简历切成版块——先看结构再决定改哪里，避免每轮都塞全文。"""
    text = resume_text or ctx.resume_text
    if not text:
        return ToolResult(ok=False, summary="没有可用的简历正文", error="resume text is empty")
    sections = split_resume_sections(text)
    if not sections:
        return ToolResult(
            ok=False,
            summary="没能识别出任何版块标题，建议改用 check_keywords 直接在全文上做关键词覆盖检查",
            error="no sections detected",
        )
    detail = {
        name: {"chars": len(value), "preview": truncate(value, 800)}
        for name, value in sections.items()
    }
    return ToolResult(
        ok=True,
        summary=f"共识别出 {len(sections)} 个版块：" + "、".join(sections.keys()),
        data={"sections": detail},
    )


async def _tool_check_keywords(ctx: ToolContext, text: str, keywords: list[str]) -> ToolResult:
    """确定性的关键词覆盖检查——ATS 筛选看的就是这个。"""
    if not keywords:
        return ToolResult(ok=False, summary="keywords 不能为空", error="missing keywords")
    if not text:
        return ToolResult(ok=False, summary="text 不能为空", error="missing text")
    present, missing = keyword_hits(text, keywords)
    coverage = round(len(present) / max(1, len(present) + len(missing)), 3)
    return ToolResult(
        ok=True,
        summary=(
            f"关键词覆盖 {len(present)}/{len(present) + len(missing)}（{coverage:.0%}）"
            + (f"，缺失：{'、'.join(missing)}" if missing else "，全部命中")
        ),
        data={
            "coverage": coverage,
            "present": present,
            "missing": missing,
        },
    )


async def _tool_search_knowledge(ctx: ToolContext, query: str, top_k: int = 3) -> ToolResult:
    """检索简历写法知识库（BM25 词项检索，非向量检索）。"""
    if not query or not query.strip():
        return ToolResult(ok=False, summary="query 不能为空", error="missing query")
    top_k = max(1, min(int(top_k or 3), 5))
    entries = load_knowledge_base()
    if not entries:
        return ToolResult(ok=False, summary="知识库为空", error="knowledge base unavailable")
    hits = bm25_search(entries, query, top_k=top_k)
    if not hits:
        return ToolResult(
            ok=True,
            summary=f"没有检索到与「{truncate(query, 40)}」相关的条目",
            data={"results": []},
        )
    results = [
        {
            "id": entry.id,
            "title": entry.title,
            "tags": entry.tags,
            "content": truncate(entry.content, 900),
            "score": round(score, 3),
        }
        for score, entry in hits
    ]
    return ToolResult(
        ok=True,
        summary=f"检索到 {len(results)} 条：" + "、".join(item["title"] for item in results),
        data={"results": results},
    )


async def _tool_recall_user_context(ctx: ToolContext) -> ToolResult:
    """读取跨任务记忆：用户偏好、最近看过的岗位、上次任务用过哪些工具。"""
    store = MemoryStore(ctx.session_factory)
    context = await store.build_context(ctx.user_id, exclude_run_id=ctx.run_id)
    preferences = context.get("preferences") or {}
    summary = (
        f"长期记忆 {len(preferences)} 条"
        + (f"（{'、'.join(list(preferences.keys())[:5])}）" if preferences else "")
        + f"；最近岗位 {len(context.get('recent_job_descriptions') or [])} 条"
        + f"；历史任务 {len(context.get('recent_runs') or [])} 次"
    )
    return ToolResult(ok=True, summary=summary, data=context)


async def _tool_remember_preference(ctx: ToolContext, key: str, value: str) -> ToolResult:
    """写入长期记忆（有上限、且不能覆盖用户手设的偏好）。"""
    store = MemoryStore(ctx.session_factory)
    ok, message = await store.set(ctx.user_id, key, value, source="agent")
    return ToolResult(
        ok=ok,
        summary=message,
        data={"key": key, "value": value, "known_keys": sorted(KNOWN_KEYS)},
        error=None if ok else message,
    )


# ---------------------------------------------------------------- 模型工具


async def _tool_score_resume_match(
    ctx: ToolContext,
    resume_text: str | None = None,
    jd_text: str | None = None,
) -> ToolResult:
    """调模型给简历和目标岗位打分（结构化 JSON，输出经 MatchReport 校验）。"""
    resume_value = resume_text or ctx.resume_text
    jd_value = jd_text or ctx.jd_text
    if not resume_value or not jd_value:
        return ToolResult(
            ok=False,
            summary="缺少简历正文或岗位 JD，无法打分",
            error="missing resume_text or jd_text",
        )
    reply = await ctx.llm.complete(
        [
            {"role": "system", "content": MATCH_SCORING_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"=== 简历（已脱敏）===\n{truncate(resume_value, 8000)}\n\n"
                    f"=== 目标岗位 ===\n{truncate(jd_value, 3000)}"
                ),
            },
        ],
        is_premium=ctx.is_premium,
        temperature=0.2,
        max_tokens=1500,
        response_format={"type": "json_object"},
    )
    data = loads_json_loose(reply.content)
    if not data:
        return ToolResult(
            ok=False,
            summary="模型没有返回可解析的 JSON 评分结果",
            error="invalid json from model",
            tokens=reply.total_tokens,
        )
    try:
        report = MatchReport(**data)
    except Exception as exc:
        return ToolResult(
            ok=False,
            summary=f"评分结果不符合预期结构：{exc}",
            error=str(exc),
            tokens=reply.total_tokens,
        )
    payload = report.model_dump()
    return ToolResult(
        ok=True,
        summary=(
            f"匹配度 {payload['overall_score']}/100，"
            f"缺失关键词 {len(payload['missing_keywords'])} 个："
            + ("、".join(payload["missing_keywords"][:8]) or "无")
        ),
        data=payload,
        tokens=reply.total_tokens,
    )


async def _tool_rewrite_resume_section(
    ctx: ToolContext,
    section_name: str,
    current_text: str | None = None,
    target_keywords: list[str] | None = None,
    style_notes: str | None = None,
) -> ToolResult:
    """改写单个版块，并用「数字必须来自原文」的确定性检查兜住编造量化成果。"""
    source_text = (current_text or "").strip()
    matched_name = None
    if not source_text:
        sections = split_resume_sections(ctx.resume_text)
        matched_name, source_text = _find_section(sections, section_name)
        if not source_text:
            return ToolResult(
                ok=False,
                summary=(
                    f"简历里没找到「{section_name}」版块，"
                    f"现有版块：{'、'.join(sections.keys()) or '（未识别出任何版块）'}"
                ),
                error="section not found",
            )

    keywords = [k for k in (target_keywords or []) if isinstance(k, str) and k.strip()][:20]
    reply = await ctx.llm.complete(
        [
            {"role": "system", "content": SECTION_REWRITE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"版块：{section_name}\n"
                    + (f"（在简历中匹配到的版块名：{matched_name}）\n" if matched_name else "")
                    + f"\n=== 该版块原文 ===\n{truncate(source_text, 4000)}\n\n"
                    + (
                        f"=== 希望融入的岗位关键词 ===\n{'、'.join(keywords)}\n\n"
                        if keywords
                        else ""
                    )
                    + (f"=== 风格要求 ===\n{truncate(style_notes, 500)}\n\n" if style_notes else "")
                    + "请按 JSON 格式输出改写结果。"
                ),
            },
        ],
        is_premium=ctx.is_premium,
        temperature=0.4,
        max_tokens=2000,
        response_format={"type": "json_object"},
    )
    data = loads_json_loose(reply.content)
    if not data or not str(data.get("rewritten") or "").strip():
        return ToolResult(
            ok=False,
            summary="模型没有返回可用的改写结果",
            error="invalid json from model",
            tokens=reply.total_tokens,
        )

    rewritten = str(data.get("rewritten")).strip()
    # 数字幻觉兜底：改写稿里出现、但原文（含整份简历）里没有的数字一律标出来。
    suspicious = unsupported_numbers(f"{source_text}\n{ctx.resume_text}", rewritten)
    payload = {
        "section": matched_name or section_name,
        "rewritten": rewritten,
        "changes": [str(x) for x in (data.get("changes") or [])][:8],
        "keywords_used": [str(x) for x in (data.get("keywords_used") or [])][:12],
        "risk_notes": [str(x) for x in (data.get("risk_notes") or [])][:8],
        "unsupported_numbers": suspicious,
    }
    summary = f"已改写「{payload['section']}」版块（{len(rewritten)} 字）"
    if suspicious:
        summary += f"；⚠️ 出现原文没有的数字：{'、'.join(suspicious)}，必须删掉或交给候选人自行确认"
    return ToolResult(ok=True, summary=summary, data=payload, tokens=reply.total_tokens)


# ---------------------------------------------------------------- 注册表


def build_registry() -> "ToolRegistry":
    """构建默认工具集。"""
    specs = [
        ToolSpec(
            name="list_resume_sections",
            description=(
                "把简历正文按版块切分，返回每个版块的名称、字数和前 800 字预览。"
                "需要看简历结构、或不确定某个版块叫什么时先调它。"
                "参数 resume_text 可省略（默认用当前简历全文）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "resume_text": {"type": "string", "description": "简历正文，省略则使用当前简历"},
                },
            },
            handler=_tool_list_resume_sections,
            timeout=10.0,
        ),
        ToolSpec(
            name="check_keywords",
            description=(
                "在给定文本里检查一批关键词是否出现，返回命中/缺失清单和覆盖率。"
                "这是确定性的字符串匹配（英文按词边界、中文按子串），不消耗模型额度。"
                "用来验证「投递这个岗位，简历还缺哪些关键词」。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要检查的文本，通常是简历正文或某个版块"},
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "关键词清单，通常取自 JD",
                    },
                },
                "required": ["text", "keywords"],
            },
            handler=_tool_check_keywords,
            timeout=10.0,
        ),
        ToolSpec(
            name="search_knowledge",
            description=(
                "检索简历写法知识库（含 STAR 写法、量化、关键词布局、应届生写法、常见雷区等条目）。"
                "当你需要「怎么写」的方法论依据时调用，返回标题 + 要点 + 相关度分数。"
                "注意：这是文档检索，不返回候选人的信息。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索词，例如「量化成果」「应届生 项目经历」"},
                    "top_k": {"type": "integer", "description": "返回条数，1-5，默认 3"},
                },
                "required": ["query"],
            },
            handler=_tool_search_knowledge,
            timeout=10.0,
        ),
        ToolSpec(
            name="recall_user_context",
            description=(
                "读取跨任务长期记忆：用户偏好（目标岗位/风格/禁忌）、最近看过的岗位、"
                "以及以往任务的执行情况。任务开始时或拿不准用户喜好时调用。"
            ),
            parameters={"type": "object", "properties": {}},
            handler=_tool_recall_user_context,
            timeout=10.0,
        ),
        ToolSpec(
            name="remember_preference",
            description=(
                "把一条跨任务有效的偏好写入长期记忆，例如用户反复强调「不要写他会 Go」。"
                "只在信息明显长期有效时才写，不要记录一次性的任务细节。"
                "常用键：target_role / target_industry / target_city / seniority / style / avoid / highlight。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "小写下划线键名，例如 avoid"},
                    "value": {"type": "string", "description": "记忆内容，尽量简短，不超过 500 字"},
                },
                "required": ["key", "value"],
            },
            handler=_tool_remember_preference,
            timeout=10.0,
        ),
        ToolSpec(
            name="score_resume_match",
            description=(
                "调模型评估简历与目标岗位的匹配度，返回 0-100 总分、命中/缺失关键词、"
                "能力差距和改进建议。需要拿到量化结论时调用。参数可省略（默认用当前简历与 JD）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "resume_text": {"type": "string", "description": "简历正文，省略则用当前简历"},
                    "jd_text": {"type": "string", "description": "岗位 JD，省略则用当前 JD"},
                },
            },
            handler=_tool_score_resume_match,
            timeout=90.0,
            llm_backed=True,
        ),
        ToolSpec(
            name="rewrite_resume_section",
            description=(
                "改写简历的某一个版块（如「项目经历」），返回改写稿、改动说明和风险提示。"
                "系统会自动检查改写稿里是否出现原文没有的数字并标出来——被标出的数字必须删掉，"
                "或改成让候选人自己补充。省略 current_text 时会自动从简历里定位该版块。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "section_name": {"type": "string", "description": "版块名，例如「项目经历」"},
                    "current_text": {"type": "string", "description": "该版块现有正文，省略则自动定位"},
                    "target_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "希望自然融入的岗位关键词",
                    },
                    "style_notes": {"type": "string", "description": "风格或篇幅要求"},
                },
                "required": ["section_name"],
            },
            handler=_tool_rewrite_resume_section,
            timeout=90.0,
            llm_backed=True,
        ),
    ]
    return ToolRegistry(specs)


class ToolRegistry:
    """工具注册表：既给模型提供 schema，也负责执行时的校验、超时与异常兜底。"""

    def __init__(self, specs: list[ToolSpec]):
        self._specs: dict[str, ToolSpec] = {spec.name: spec for spec in specs}

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def names(self) -> list[str]:
        return list(self._specs)

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def schemas(self) -> list[dict]:
        """转成 OpenAI 兼容的 tools 参数。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self._specs.values()
        ]

    def menu(self) -> str:
        """给规划器看的一行式工具清单。"""
        return "\n".join(
            f"- {spec.name}：{spec.description.split('。')[0]}。" for spec in self._specs.values()
        )

    def coerce_args(self, spec: ToolSpec, args: dict | None) -> tuple[dict, str | None]:
        """按 schema 收敛参数：类型转换、长度/条数上限、必填校验。"""
        schema = spec.parameters or {}
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        incoming = args if isinstance(args, dict) else {}
        coerced: dict = {}

        for name, prop in properties.items():
            if name not in incoming or incoming[name] is None:
                continue
            value = incoming[name]
            declared = prop.get("type")
            if declared == "integer":
                if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                    return {}, f"参数 {name} 需要整数，收到 {type(value).__name__}"
                try:
                    value = int(float(str(value).strip()))
                except (TypeError, ValueError):
                    return {}, f"参数 {name} 需要整数，收到 {value!r}"
            elif declared == "number":
                try:
                    value = float(str(value).strip())
                except (TypeError, ValueError):
                    return {}, f"参数 {name} 需要数字，收到 {value!r}"
            elif declared == "string":
                if not isinstance(value, str):
                    value = str(value)
                if len(value) > _MAX_ARG_CHARS:
                    value = value[:_MAX_ARG_CHARS]
            elif declared == "array":
                if isinstance(value, str):
                    # 模型经常把数组写成 "a, b, c"，这里直接容错拆开而不是判错。
                    value = [part.strip() for part in re.split(r"[,，、;；\n]", value) if part.strip()]
                if not isinstance(value, list):
                    return {}, f"参数 {name} 需要数组"
                value = value[:_MAX_ARRAY_ITEMS]
            coerced[name] = value

        missing = [name for name in required if not coerced.get(name)]
        if missing:
            return {}, (
                f"缺少必填参数：{'、'.join(missing)}。"
                f"本工具参数：{json.dumps(properties, ensure_ascii=False)[:400]}"
            )
        return coerced, None

    async def execute(
        self,
        name: str,
        args: dict | None,
        ctx: ToolContext,
        timeout: float | None = None,
    ) -> ToolResult:
        spec = self._specs.get(name)
        if spec is None:
            return ToolResult(
                ok=False,
                summary=f"未知工具「{name}」",
                error=f"未知工具；可选工具：{', '.join(self._specs)}",
            )
        coerced, error = self.coerce_args(spec, args)
        if error:
            return ToolResult(ok=False, summary=error, error=error)
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                spec.handler(ctx, **coerced), timeout=timeout or spec.timeout
            )
        except asyncio.TimeoutError:
            return ToolResult(
                ok=False,
                summary=f"工具 {name} 超时（{timeout or spec.timeout:.0f}s）",
                error="timeout",
            )
        except Exception as exc:
            logger.warning(
                "agent: tool %s failed after %.0fms => %s: %s",
                name,
                (time.perf_counter() - started) * 1000,
                type(exc).__name__,
                exc,
            )
            return ToolResult(
                ok=False,
                summary=f"工具 {name} 执行失败：{type(exc).__name__}: {exc}",
                error=f"{type(exc).__name__}: {exc}",
            )
        return result
