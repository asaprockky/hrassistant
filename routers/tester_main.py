import math
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketException, status
from sqlalchemy.orm import Session, joinedload

# Import your database and models
from database.database import get_db
from database.models import User, TestSession, Company 
from routers.login import get_current_user, get_current_user_from_token
from schemas.user_schema import PaginatedTests

router = APIRouter(prefix="/testing/sessions", tags=["Test Sessions"])

# ==========================================
# HELPER FUNCTIONS & DEPENDENCIES
# ==========================================

def get_company_name(db: Session, company_id: uuid.UUID) -> str:
    """Fetches the company name using its ID."""
    company = db.query(Company.name).filter(Company.id == company_id).first()
    return company[0] if company else "Unknown Company"

async def get_current_user_ws(websocket: WebSocket, token: str, db: Session = Depends(get_db)):
    """Dependency for WebSocket connections."""
    user = get_current_user_from_token(token, db)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return user

def format_test_session(session: TestSession) -> dict:
    """Helper function to unify the response format to strict camelCase."""
    if session.user and session.user.company_id:
        company_name = session.user.company.name if session.user.company else "Unknown Company"
    else:
        company_name = "Unassigned Test"
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
        "title": session.practice.title,
        "createdBy": company_name,
        "createdAt": session.started_time,  
        "deadline": session.practice.deadline,
        "score": score,
        "status": status_text,
        "statusLabel": status_label,
        "actionUrl": action_url
    }

# ==========================================
# ENDPOINTS
# ==========================================

@router.get("/active", response_model=PaginatedTests)
def get_active_tests(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    """Retrieves a paginated list of active tests assigned to the user."""
    base_query = db.query(TestSession).options(
        joinedload(TestSession.practice),
        joinedload(TestSession.user).joinedload(User.company),
    ).filter(
        TestSession.user_id == user.id,
        TestSession.is_finished == False
    ).order_by(TestSession.started_time.desc())
    
    total_items = base_query.count()
    offset = (page - 1) * size
    active_tests = base_query.offset(offset).limit(size).all()
    
    return {
        "items": [format_test_session(t) for t in active_tests],
        "total": total_items,
        "page": page,
        "size": size,
        "totalPages": math.ceil(total_items / size) if total_items > 0 else 0
    }

@router.get("/completed", response_model=PaginatedTests)
def get_test_history(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    """Retrieves a paginated list of finished test sessions assigned to the user."""
    base_query = db.query(TestSession).options(
        joinedload(TestSession.practice),
        joinedload(TestSession.user).joinedload(User.company),
    ).filter(
        TestSession.user_id == user.id, 
        TestSession.is_finished == True
    ).order_by(TestSession.started_time.desc())

    total_items = base_query.count()
    offset = (page - 1) * size
    completed_tests = base_query.offset(offset).limit(size).all()
        
    return {
        "items": [format_test_session(t) for t in completed_tests],
        "total": total_items,
        "page": page,
        "size": size,
        "totalPages": math.ceil(total_items / size) if total_items > 0 else 0
    }

@router.get("/all", response_model=PaginatedTests)
def get_all_tests(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    """Retrieves a paginated list of ALL test sessions (both active and completed)."""
    base_query = db.query(TestSession).options(
        joinedload(TestSession.practice),
        joinedload(TestSession.user).joinedload(User.company),
    ).filter(
        TestSession.user_id == user.id
    ).order_by(TestSession.started_time.desc())

    total_items = base_query.count()
    offset = (page - 1) * size
    all_sessions = base_query.offset(offset).limit(size).all()
        
    return {
        "items": [format_test_session(t) for t in all_sessions],
        "total": total_items,
        "page": page,
        "size": size,
        "totalPages": math.ceil(total_items / size) if total_items > 0 else 0
    }
