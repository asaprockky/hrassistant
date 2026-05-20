import math
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

# Import your database and models
from database.database import get_db
from database.models import User, TestSession
from routers.login import get_current_user
from schemas.user_schema import PaginatedTests

router = APIRouter(prefix="/testing/sessions", tags=["Test Sessions"])

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def format_test_session(session: TestSession) -> dict:
    """Format a TestSession into the API response shape.

    Caller MUST eager-load `session.user.company` and `session.practice` so
    this function never triggers extra queries (avoids per-row N+1).
    """
    company = session.user.company if session.user else None
    company_name = company.name if company else "Unassigned Test"

    practice = session.practice
    score = int(session.overall_points or 0)
    is_finished = session.is_finished

    if is_finished:
        status_label = f"Passed ({score}%)" if score >= 60 else "Failed"
        status_text = "Completed"
        action_url = f"/reports/{session.session_id}"
    else:
        status_label = "Active"
        status_text = "Active"
        action_url = f"/test/{session.session_id}"

    return {
        "testId": str(session.session_id),
        "title": practice.title if practice else "",
        "createdBy": company_name,
        "createdAt": session.started_time,
        "deadline": practice.deadline if practice else None,
        "score": score,
        "status": status_text,
        "statusLabel": status_label,
        "actionUrl": action_url,
    }


def _paginate_sessions(
    db: Session,
    user_id: uuid.UUID,
    page: int,
    size: int,
    is_finished: Optional[bool],
) -> dict:
    """Shared logic to paginate TestSession rows with eager-loaded relations."""
    filters = [TestSession.user_id == user_id]
    if is_finished is not None:
        filters.append(TestSession.is_finished == is_finished)

    total_items = (
        db.query(TestSession)
        .filter(*filters)
        .with_entities(TestSession.session_id)
        .count()
    )

    if total_items == 0:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "size": size,
            "totalPages": 0,
        }

    offset = (page - 1) * size
    sessions = (
        db.query(TestSession)
        .options(
            joinedload(TestSession.user).joinedload(User.company),
            joinedload(TestSession.practice),
        )
        .filter(*filters)
        .order_by(TestSession.started_time.desc())
        .offset(offset)
        .limit(size)
        .all()
    )

    return {
        "items": [format_test_session(t) for t in sessions],
        "total": total_items,
        "page": page,
        "size": size,
        "totalPages": math.ceil(total_items / size),
    }


# ==========================================
# ENDPOINTS
# ==========================================

@router.get("/active", response_model=PaginatedTests)
def get_active_tests(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieves a paginated list of active tests assigned to the user."""
    return _paginate_sessions(db, user.id, page, size, is_finished=False)


@router.get("/completed", response_model=PaginatedTests)
def get_test_history(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieves a paginated list of finished test sessions assigned to the user."""
    return _paginate_sessions(db, user.id, page, size, is_finished=True)


@router.get("/all", response_model=PaginatedTests)
def get_all_tests(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieves a paginated list of ALL test sessions (both active and completed)."""
    return _paginate_sessions(db, user.id, page, size, is_finished=None)
