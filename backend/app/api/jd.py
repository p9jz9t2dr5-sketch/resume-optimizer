"""职位描述（JD）路由（挂载前缀 /jd，最终路径 /api/jd/*）。

| 方法 | 路径 | 说明 | 需要登录 |
|------|------|------|----------|
| POST | /parse | 把 JD 解析成结构化要求，并与指定简历做匹配度分析（评分 / 命中与缺失关键词 / 改进建议） | 是 |
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.models.job_description import JobDescription
from app.schemas.jd import JDParseRequest, JDParseResponse, ParsedRequirement
from app.services.llm_service import llm_service
from app.services.resume_service import get_resume_by_id

router = APIRouter()


@router.post("/parse", response_model=JDParseResponse)
async def parse_jd(
    request: JDParseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解析职位描述并与简历做匹配度分析。

    入参：raw_text（JD 原文）+ 可选 resume_id（传了才会和简历对比）
    返回：结构化要求 + 匹配报告（overall_score 评分、matched/missing 关键词、
          skill_gaps 能力差距、suggestions 改进建议）
    说明：模型输出并不稳定（评分可能是 87.5 或 "92"），由 app/schemas/jd.py
          的校验器负责容错与取整。
    异常：未配置模型 Key → 503
    """
    # Parse JD with AI
    try:
        parsed = await llm_service.parse_jd(request.raw_text, current_user.is_premium)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI service error: {str(e)}",
        )

    reqs = parsed.get("parsed_requirements", {})

    # Save to DB
    jd = JobDescription(
        user_id=current_user.id,
        source_type="pasted",
        company_name=parsed.get("company_name"),
        title=parsed.get("title"),
        raw_text=request.raw_text,
        parsed_requirements=reqs,
    )
    db.add(jd)
    await db.flush()
    await db.refresh(jd)

    response = JDParseResponse(
        id=jd.id,
        company_name=jd.company_name,
        title=jd.title,
        parsed_requirements=ParsedRequirement(**reqs) if reqs else ParsedRequirement(),
    )

    # If resume_id provided, also run match analysis
    if request.resume_id:
        try:
            resume = await get_resume_by_id(db, uuid.UUID(request.resume_id), current_user.id)
        except ValueError:
            resume = None
        if resume and (resume.content or resume.anonymized_text):
            try:
                match_report = await llm_service.analyze_match(
                    resume.content or resume.anonymized_text, reqs, current_user.is_premium
                )
                response.match_report = match_report
            except Exception:
                pass  # Match analysis is optional

    return response
