"""简历相关的请求/响应模型：上传结果、简历列表、结构化数据、优化建议请求。"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class PolishRequest(BaseModel):
    jd_text: str
    match_report: Optional[dict] = None


class EducationItem(BaseModel):
    school: Optional[str] = None
    degree: Optional[str] = None
    major: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None


class WorkItem(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    description: Optional[str] = None


class ProjectItem(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    description: Optional[str] = None
    tech_stack: list[str] = Field(default_factory=list)


class ResumeStructured(BaseModel):
    basic_info: dict = Field(default_factory=dict)
    summary: Optional[str] = None
    education: list[EducationItem] = Field(default_factory=list)
    work_experience: list[WorkItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certificates: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    class Config:
        extra = "ignore"


class ResumeUploadResponse(BaseModel):
    id: uuid.UUID
    version_name: str
    original_filename: str
    content: Optional[str]
    anonymized_text: Optional[str]
    original_file_url: Optional[str] = None
    avatar_url: Optional[str] = None
    parsed_data: dict
    created_at: datetime

    class Config:
        from_attributes = True


class ResumeResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    version_name: str
    original_filename: str
    content: Optional[str]
    anonymized_text: Optional[str]
    original_file_url: Optional[str] = None
    avatar_url: Optional[str] = None
    parsed_data: dict
    created_at: datetime

    class Config:
        from_attributes = True


class ResumeListResponse(BaseModel):
    resumes: list[ResumeResponse]
    total: int
