import math
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketException, status
from sqlalchemy.orm import Session

# Import your database and models
from database.database import get_db
from database.models import User, TestSession, Company 
from routers.login import get_current_user, get_current_user_from_token
from schemas.user_schema import PaginatedActiveTests, PaginatedAllTests, PaginatedCompletedTests

router = APIRouter(prefix="/testing/sessions", tags=["Test Sessions"])

# ==========================================
# 1. PYDANTIC SCHEMAS (Response Models)
# ==========================================


# ==========================================
# 2. HELPER FUNCTIONS & DEPENDENCIES
# ==========================================

def get_company_name(db: Session, company_id: uuid.UUID) -> str:
    """Fetches the company name using its ID."""
    company = db.query(Company.name).filter(Company.id == company_id).first()
    return company[0] if company else "Unknown Company"

async def get_current_user_ws(websocket: WebSocket, token: str):
    """Dependency for WebSocket connections."""
    user = get_current_user_from_token(token)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return user

# ==========================================
# 3. ENDPOINTS
# ==========================================

@router.get("/active", response_model=PaginatedActiveTests)
def get_active_tests(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    """Retrieves a paginated list of active tests assigned to the user."""
    
    base_query = db.query(TestSession).filter(
        TestSession.user_id == user.id,
        TestSession.is_finished == False
    ).order_by(TestSession.started_time.desc())
    
    total_items = base_query.count()
    offset = (page - 1) * size
    active_tests = base_query.offset(offset).limit(size).all()
    
    tests_summary = []
    for t in active_tests:
        company_name = get_company_name(db, t.user.company_id) if t.user.company_id else "Unassigned Test"
        tests_summary.append({
            "test_id": str(t.session_id), 
            "test_title": t.practice.title, 
            "created_by": company_name, 
            "created_at": t.started_time, 
            "deadline": t.practice.deadline, 
            "final_score": t.overall_points 
        })
    
    return {
        "items": tests_summary,
        "total": total_items,
        "page": page,
        "size": size,
        "total_pages": math.ceil(total_items / size) if total_items > 0 else 0
    }


@router.get("/completed", response_model=PaginatedCompletedTests)
def get_test_history(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    """Retrieves a paginated list of finished test sessions assigned to the user."""
    
    base_query = db.query(TestSession).filter(
        TestSession.user_id == user.id, 
        TestSession.is_finished == True
    ).order_by(TestSession.started_time.desc())

    total_items = base_query.count()
    offset = (page - 1) * size
    all_sessions = base_query.offset(offset).limit(size).all()

    history_summaries = []
    for session in all_sessions: 
        score = int(session.overall_points or 0)
        history_summaries.append({
            "test_id": str(session.session_id),
            "assessment_name": session.practice.title,
            "date": session.started_time.strftime("%b %d, %Y") if session.started_time else None,
            "score": score,
            "status_label": f"Passed ({score}%)" if score >= 60 else "Failed",
            "action_url": f"/reports/{session.session_id}"
        })
        
    return {
        "items": history_summaries,
        "total": total_items,
        "page": page,
        "size": size,
        "total_pages": math.ceil(total_items / size) if total_items > 0 else 0
    }


@router.get("/all", response_model=PaginatedAllTests)
def get_all_tests(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    """Retrieves a paginated list of ALL test sessions (both active and completed)."""
    
    # Notice: No `is_finished` filter here, so we get everything
    base_query = db.query(TestSession).filter(
        TestSession.user_id == user.id
    ).order_by(TestSession.started_time.desc())

    total_items = base_query.count()
    offset = (page - 1) * size
    all_sessions = base_query.offset(offset).limit(size).all()

    all_summaries = []
    for session in all_sessions: 
        company_name = get_company_name(db, session.user.company_id) if session.user.company_id else "Unassigned Test"
        score = int(session.overall_points or 0)
        
        # Determine human-readable status
        if session.is_finished:
            status_text = "Completed"
        else:
            status_text = "Active"

        all_summaries.append({
            "test_id": str(session.session_id),
            "assessment_name": session.practice.title,
            "created_by": company_name,
            "date": session.started_time.strftime("%b %d, %Y") if session.started_time else None,
            "status": status_text,
            "score": score,
            "action_url": f"/reports/{session.session_id}" if session.is_finished else f"/test/{session.session_id}" 
        })
        
    return {
        "items": all_summaries,
        "total": total_items,
        "page": page,
        "size": size,
        "total_pages": math.ceil(total_items / size) if total_items > 0 else 0
    }