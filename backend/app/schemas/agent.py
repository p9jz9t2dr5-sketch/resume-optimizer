"""Agent 相关的请求/响应模型。

轨迹里的 ``tool_input`` / ``tool_output`` 直接返回给前端渲染「AI 干了什么」，
所以字段名与 ``agent_steps`` 表保持一致，省掉一层映射。
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AgentOptimizeRequest(BaseModel):
    resume_id: str
    jd_text: str
    match_report: Optional[dict] = None
    # 覆盖服务端默认步数上限（1–12），便于前端做「深度分析」模式
    max_steps: Optional[int] = Field(default=None, ge=1, le=12)


class AgentStepResponse(BaseModel):
    step_index: int
    kind: str
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_output: Optional[dict] = None
    status: str
    error: Optional[str] = None
    latency_ms: int
    tokens: int
    created_at: datetime

    class Config:
        from_attributes = True


class AgentRunResponse(BaseModel):
    id: uuid.UUID
    resume_id: Optional[uuid.UUID] = None
    goal: Optional[str] = None
    status: str
    stopped_reason: Optional[str] = None
    model: Optional[str] = None
    plan: list = Field(default_factory=list)
    steps_count: int
    tool_calls: int
    prompt_tokens: int
    completion_tokens: int
    duration_ms: int
    error: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgentRunDetailResponse(AgentRunResponse):
    final_output: Optional[str] = None
    steps: list[AgentStepResponse] = Field(default_factory=list)


class AgentRunListResponse(BaseModel):
    runs: list[AgentRunResponse]
    total: int


class PreferenceResponse(BaseModel):
    key: str
    value: str
    source: str
    updated_at: datetime

    class Config:
        from_attributes = True


class PreferenceListResponse(BaseModel):
    preferences: list[PreferenceResponse]
    total: int
    known_keys: dict[str, str] = Field(default_factory=dict)


class PreferenceUpsertRequest(BaseModel):
    value: str = Field(min_length=1, max_length=500)
