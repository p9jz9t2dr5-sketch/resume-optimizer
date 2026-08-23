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
