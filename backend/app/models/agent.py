"""agent_runs / agent_steps / user_preferences：Agent 的一次执行、它的执行轨迹与长期记忆。

三张表各司其职：

- ``agent_runs``：一次「让 Agent 优化简历」的任务（目标、计划、状态、耗时、token 用量、最终产出）
- ``agent_steps``：这次任务的执行轨迹（规划 / 工具调用 / 上下文压缩 / 重规划 / 收尾），
  按 ``step_index`` 排序逐个落库，流式过程中随时可查——中途断开也留有半程轨迹
- ``user_preferences``：跨任务的长期记忆（目标岗位、风格偏好、禁忌等），
  由用户显式设置或 Agent 通过 ``remember_preference`` 工具写入

状态字段刻意用 ``String`` 而不是数据库枚举：SQLite 与 Postgres 对 ENUM 的
DDL 支持不一致，迁移需要在这两个库上都保持零差异。
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgentRunStatus:
    """agent_runs.status 的取值。"""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AgentStepKind:
    """agent_steps.kind 的取值。"""

    PLAN = "plan"
    TOOL = "tool"
    REPLAN = "replan"
    COMPACTION = "compaction"
    FINAL = "final"
    ERROR = "error"


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 简历被删除时置空（与 chat_sessions.resume_id 同样的约定），轨迹本身保留。
    resume_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True
    )
    goal: Mapped[str] = mapped_column(Text, nullable=True)
    jd_text: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=AgentRunStatus.RUNNING)
    # 停止原因：completed / max_steps / tool_unsupported / error
    stopped_reason: Mapped[str] = mapped_column(String(32), nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=True)
    plan: Mapped[list] = mapped_column(JSON, default=list)
    steps_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    final_output: Mapped[str] = mapped_column(Text, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )

    steps = relationship(
        "AgentStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentStep.step_index",
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=True)
    tool_input: Mapped[dict] = mapped_column(JSON, nullable=True)
    tool_output: Mapped[dict] = mapped_column(JSON, nullable=True)
    # ok / error
    status: Mapped[str] = mapped_column(String(20), default="ok")
    error: Mapped[str] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    run = relationship("AgentRun", back_populates="steps")


class UserPreference(Base):
    """长期记忆：一个用户一条键值，``source`` 区分「用户自己设的」和「Agent 记住的」。"""

    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_preferences_user_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    # user / agent
    source: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )
