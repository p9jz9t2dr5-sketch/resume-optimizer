from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import uuid


class JDParseRequest(BaseModel):
    raw_text: str
    resume_id: Optional[str] = None


class ParsedRequirement(BaseModel):
    skills: list[str] = Field(default_factory=list)
    experience_years: Optional[str] = None
    education: Optional[str] = None
    responsibilities: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class MatchReport(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    @field_validator("overall_score", mode="before")
    @classmethod
    def _coerce_score(cls, v):
        # LLMs sometimes return floats/strings like 87.5 or "88"; coerce safely.
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return 0


class JDParseResponse(BaseModel):
    id: uuid.UUID
    company_name: Optional[str]
    title: Optional[str]
    parsed_requirements: ParsedRequirement
    match_report: Optional[MatchReport] = None

    class Config:
        from_attributes = True
