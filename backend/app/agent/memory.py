"""Agent 的长期记忆：跨任务保存的用户偏好。

记忆分两层，这里管的是「长期」那一层：

- 短期记忆 = 单次任务内的上下文，超出预算由 ``loop.py`` 压缩成摘要
- 长期记忆 = ``user_preferences`` 表，跨任务保留，每次执行前注入 system prompt

两个刻意的设计约束：

1. **写入有上限**（``AGENT_MAX_PREFERENCES``）。Agent 会自己往记忆里写东西，
   没有上限的话跑几十次之后记忆就变成噪声，反而污染每一次的 prompt。
2. **区分来源**（``user`` / ``agent``）。用户自己设的偏好不能被 Agent 的自
   动推断覆盖掉——除非用户重新设置。前端也据此把「你自己设的」和「AI 记住的」分开显示。
"""

import logging
import re
import uuid
from typing import Callable

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models.agent import AgentRun, AgentStep, UserPreference
from app.models.job_description import JobDescription

settings = get_settings()
logger = logging.getLogger("uvicorn")

# 键名限制在 ASCII 小写下划线，既避免注入奇怪字符，也便于前端做固定表单。
_PREFERENCE_KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_MAX_VALUE_LEN = 500

# 约定俗成的键（不是白名单，只是让 prompt 和前端有统一的语义；其它合法键也允许写）
KNOWN_KEYS: dict[str, str] = {
    "target_role": "目标岗位",
    "target_industry": "目标行业",
    "target_city": "目标城市",
    "seniority": "经验级别（应届/实习/社招）",
    "style": "写作风格偏好",
    "avoid": "不要在简历里出现的内容",
    "highlight": "希望重点突出的优势",
    "language": "简历语言",
}


class MemoryStore:
    """封装 user_preferences 的读写，全部走短生命周期会话（SSE 流中安全）。"""

    def __init__(self, session_factory: Callable):
        self.session_factory = session_factory

    async def load(self, user_id: uuid.UUID) -> dict[str, str]:
        """读出该用户的全部长期记忆：``{key: value}``。"""
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(UserPreference)
                    .where(UserPreference.user_id == user_id)
                    .order_by(UserPreference.updated_at.desc())
                )
            ).scalars().all()
        return {row.key: row.value for row in rows}

    async def set(
        self,
        user_id: uuid.UUID,
        key: str,
        value: str,
        source: str = "agent",
    ) -> tuple[bool, str]:
        """写入/覆盖一条记忆。返回 ``(是否成功, 给模型看的说明文字)``。

        失败不是异常而是返回值：Agent 需要看到「为什么没存进去」，才能换个做法。
        """
        # 键名不做大小写折叠：「Target_Role」和「target_role」应当是同一个键还是两个，
        # 与其替调用方猜，不如直接拒绝并说明规则——接口契约清楚，Agent 也会照着重试。
        normalized_key = (key or "").strip()
        normalized_value = (value or "").strip()

        if not _PREFERENCE_KEY.match(normalized_key):
            return False, (
                "记忆键名不合法：只能是 2–41 位的小写字母/数字/下划线，且以字母开头。"
                f"常用键：{', '.join(sorted(KNOWN_KEYS))}"
            )
        if not normalized_value:
            return False, "记忆内容不能为空"
        if len(normalized_value) > _MAX_VALUE_LEN:
            return False, f"记忆内容过长（{len(normalized_value)} 字），请压缩到 {_MAX_VALUE_LEN} 字以内"

        async with self.session_factory() as session:
            existing = await session.scalar(
                select(UserPreference).where(
                    UserPreference.user_id == user_id, UserPreference.key == normalized_key
                )
            )
            if existing is None:
                count = await session.scalar(
                    select(func.count()).where(UserPreference.user_id == user_id)
                )
                if (count or 0) >= settings.AGENT_MAX_PREFERENCES:
                    return False, (
                        f"记忆已满（上限 {settings.AGENT_MAX_PREFERENCES} 条）。"
                        "请先覆盖已有键，或提醒用户去「偏好设置」里清理。"
                    )
                session.add(
                    UserPreference(
                        user_id=user_id, key=normalized_key, value=normalized_value, source=source
                    )
                )
            elif existing.source == "user" and source == "agent":
                # 用户手设的偏好优先级最高，Agent 不能悄悄改掉它。
                return False, f"「{normalized_key}」是用户自己设置的偏好，Agent 不能覆盖"
            else:
                existing.value = normalized_value
                existing.source = source
            try:
                await session.commit()
            except IntegrityError:
                # 并发写入撞上唯一约束：退化成更新，不算失败。
                await session.rollback()
                async with self.session_factory() as retry:
                    row = await retry.scalar(
                        select(UserPreference).where(
                            UserPreference.user_id == user_id,
                            UserPreference.key == normalized_key,
                        )
                    )
                    if row is None:
                        return False, "写入记忆失败，请重试"
                    row.value = normalized_value
                    await retry.commit()
        return True, f"已记住：{normalized_key} = {normalized_value}"

    async def remove(self, user_id: uuid.UUID, key: str) -> bool:
        """删掉一条记忆，返回是否真的删到了。"""
        async with self.session_factory() as session:
            result = await session.execute(
                delete(UserPreference).where(
                    UserPreference.user_id == user_id, UserPreference.key == key
                )
            )
            await session.commit()
        return bool(result.rowcount)

    async def build_context(
        self,
        user_id: uuid.UUID,
        *,
        limit_jds: int = 3,
        limit_runs: int = 3,
        exclude_run_id: uuid.UUID | None = None,
    ) -> dict:
        """给 ``recall_user_context`` 工具用的记忆快照。

        除了偏好本身，还带上「最近看过的岗位」和「最近几次 Agent 任务用过哪些工具」——
        后者让 Agent 知道自己上次是什么路子，避免每次从零开始。
        """
        async with self.session_factory() as session:
            preferences = {
                row.key: row.value
                for row in (
                    await session.execute(
                        select(UserPreference)
                        .where(UserPreference.user_id == user_id)
                        .order_by(UserPreference.updated_at.desc())
                    )
                ).scalars().all()
            }

            jd_rows = (
                await session.execute(
                    select(JobDescription)
                    .where(JobDescription.user_id == user_id)
                    .order_by(JobDescription.created_at.desc())
                    .limit(limit_jds)
                )
            ).scalars().all()

            run_rows = (
                await session.execute(
                    select(AgentRun)
                    .where(AgentRun.user_id == user_id)
                    .order_by(AgentRun.created_at.desc())
                    .limit(limit_runs)
                )
            ).scalars().all()
            # 「历史任务」应当是真正的历史：本次任务在建工具上下文时已经落库，
            # 不过滤的话 Agent 会把自己这一次算进历史，看到的记录是错的。
            if exclude_run_id is not None:
                run_rows = [row for row in run_rows if row.id != exclude_run_id]

            tools_by_run: dict[uuid.UUID, list[str]] = {}
            if run_rows:
                step_rows = await session.execute(
                    select(AgentStep.run_id, AgentStep.tool_name).where(
                        AgentStep.run_id.in_([row.id for row in run_rows]),
                        AgentStep.kind == "tool",
                    )
                )
                for run_id, tool_name in step_rows.all():
                    if not tool_name:
                        continue
                    bucket = tools_by_run.setdefault(run_id, [])
                    if tool_name not in bucket:
                        bucket.append(tool_name)

        return {
            "preferences": preferences,
            "recent_job_descriptions": [
                {
                    "title": row.title,
                    "company": row.company_name,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in jd_rows
            ],
            "recent_runs": [
                {
                    "goal": (row.goal or "")[:120],
                    "status": row.status,
                    "stopped_reason": row.stopped_reason,
                    "steps": row.steps_count,
                    "tools_used": tools_by_run.get(row.id, []),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in run_rows
            ],
        }

    async def render_for_prompt(self, user_id: uuid.UUID, limit: int = 800) -> str:
        """把长期记忆渲染成 system prompt 里的短段落（超长则截断）。"""
        try:
            preferences = await self.load(user_id)
        except Exception as exc:  # 记忆读不到不该让整个任务挂掉
            logger.warning("memory: load preferences failed => %s: %s", type(exc).__name__, exc)
            return ""
        if not preferences:
            return ""
        lines = []
        for key, value in preferences.items():
            label = KNOWN_KEYS.get(key, key)
            lines.append(f"- {label}（{key}）：{value}")
        text = "\n".join(lines)
        if len(text) > limit:
            text = text[:limit] + "…"
        return text
