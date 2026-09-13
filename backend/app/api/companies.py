"""公司库路由（挂载前缀 /companies，最终路径 /api/companies/*）。

| 方法 | 路径 | 说明 | 需要登录 |
|------|------|------|----------|
| GET | / | 公司列表（分页） | 否 |
| GET | /search | 按关键词搜索公司（返回常见岗位，可用于生成 JD 草稿） | 否 |

数据来源：backend/app/seed_data.py，首次启动时自动写入 50+ 家公司。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.company import Company
from app.schemas.company import CompanyResponse, CompanySearchResponse

router = APIRouter()


@router.get("/search", response_model=CompanySearchResponse)
async def search_companies(
    q: str = Query(default="", description="Search query for company name"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """按关键词搜索公司（公开接口，无需登录）。

    入参：q 关键词、page 页码、page_size（1–100）
    返回：{companies, total, page, page_size}，每条含公司名、行业、官网与常见岗位。
    """
    query = select(Company)

    # Dialect-agnostic case-insensitive match (works on both Postgres and SQLite)
    if q:
        query = query.where(func.lower(Company.name).like(f"%{q.lower()}%"))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Paginate
    offset = (page - 1) * page_size
    result = await db.execute(
        query.offset(offset).limit(page_size).order_by(Company.name.asc())
    )
    companies = result.scalars().all()

    return CompanySearchResponse(
        companies=[CompanyResponse.model_validate(c) for c in companies],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=CompanySearchResponse)
async def list_companies(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """公司列表（公开接口，无需登录），按公司名升序分页返回。"""
    query = select(Company).order_by(Company.name.asc())
    count_query = select(func.count()).select_from(Company)
    total = await db.scalar(count_query) or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    companies = result.scalars().all()

    return CompanySearchResponse(
        companies=[CompanyResponse.model_validate(c) for c in companies],
        total=total,
        page=page,
        page_size=page_size,
    )
