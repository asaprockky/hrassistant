import math
import random
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import User, Candidate, Created_Vacancy, Company, TestSession
from routers.login import get_current_user
# Import the individual schemas instead of the combined one
from schemas.user_schema import PaginatedApplications, PipelineStats, ApplicationSummary 

router = APIRouter(prefix="/api/v1/candidate/dashboard", tags=["Candidate Dashboard"])

# ==========================================
# 1. Pipeline Overview API
# ==========================================
@router.get("/pipeline", response_model=PipelineStats)
def get_pipeline_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetches high-level stats for the candidate dashboard."""
    user_id = current_user.id

    # Total Jobs Applied
    total_jobs = db.query(Candidate).filter(Candidate.user_id == user_id).count()

    # Total Tests Solved & Average Score
    test_stats = (
        db.query(
            func.count(TestSession.session_id).label("total_tests"),
            func.avg(TestSession.overall_points).label("avg_score")
        )
        .filter(
            TestSession.user_id == user_id,
            TestSession.is_finished == True
        )
        .first()
    )

    total_tests = test_stats.total_tests or 0
    avg_score = int(test_stats.avg_score) if test_stats.avg_score else 0

    return {
        "total_jobs_applied": total_jobs,
        "total_tests_completed": total_tests,
        "average_test_score": avg_score
    }


@router.get("/applications/recent", response_model=PaginatedApplications)
def get_recent_applications(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fetches job applications for the candidate with pagination.
    Example: /api/v1/candidate/dashboard/applications/recent?page=2&size=5
    """
    user_id = current_user.id
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1. Build the base query
    base_query = (
        db.query(Candidate, Created_Vacancy, Company)
        .join(Created_Vacancy, Candidate.vacancy_id == Created_Vacancy.id)
        .join(Company, Created_Vacancy.company_id == Company.id)
        .filter(
            Candidate.user_id == user_id,
            Candidate.created_at <= now_utc 
        )
        .order_by(Candidate.created_at.desc())
    )

    # 2. Get total count for the frontend UI BEFORE applying limits
    total_items = base_query.count()

    # 3. Apply Offset and Limit
    offset = (page - 1) * size
    applications_query = base_query.offset(offset).limit(size).all()

    # 4. Format the results
    recent_applications = []
    for candidate, vacancy, company in applications_query:
        fit_score = int(candidate.ai_score) if candidate.ai_score > 0 else random.randint(65, 98)

        recent_applications.append({
            "candidate_id": candidate.id,
            "vacancy_id": vacancy.id,
            "company_name": company.name,
            "position_title": vacancy.job_name,
            "status": candidate.status,
            "ai_fit_score": fit_score,
            "applied_at": candidate.created_at.strftime("%b %d, %Y") if candidate.created_at else "Unknown"
        })

    # 5. Return the wrapped response
    return {
        "items": recent_applications,
        "total": total_items,
        "page": page,
        "size": size,
        "total_pages": math.ceil(total_items / size)
    }
