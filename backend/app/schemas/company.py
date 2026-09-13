"""公司库的响应模型。"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class CompanyResponse(BaseModel):
    id: int
    name: str
    official_site: Optional[str]
    industry: Optional[str]
    description: Optional[str]
    common_positions: list[str]
    logo_url: Optional[str]

    class Config:
        from_attributes = True


class CompanySearchResponse(BaseModel):
    companies: list[CompanyResponse]
    total: int
    page: int
    page_size: int
