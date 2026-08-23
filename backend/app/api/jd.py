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
