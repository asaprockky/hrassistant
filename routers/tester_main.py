from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from database.database import get_db
from sqlalchemy.orm import Session
# IMPORT CORRECTION: Replace StartedTest with the new TestSession model
from database.models import User, TestSession, Company 
from routers.login import get_current_user
import uuid

from fastapi import WebSocket, WebSocketException, status
# Assuming you have a function that decodes JWTs and returns a user
from routers.login import get_current_user_from_token

router = APIRouter(prefix="/api/v1/testing/sessions", tags=["Test Sessions"])

# Helper function to query the Company model for relationships
def get_company_name(db: Session, company_id: uuid.UUID) -> str:
    """Fetches the company name using its ID."""
    company = db.query(Company.name).filter(Company.id == company_id).first()
    return company[0] if company else "Unknown Company"




async def get_current_user_ws(websocket: WebSocket, token: str):
    user = get_current_user_from_token(token) # Replace with your actual token decoding logic
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    return user

@router.get("/active")
def get_active_tests(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Retrieves a list of tests assigned to the user that are currently active (not finished).
    """
    
    # 1. QUERY CORRECTION: Use TestSession instead of StartedTest
    active_tests = db.query(TestSession).filter(
        TestSession.user_id == user.id,
        TestSession.is_finished == False, # Use the correct column for "active" state
        # The deadline check (optional but recommended): 
        # For simplicity, we assume 'is_finished' handles test state
    ).all()
    
    if not active_tests:
        return {"message": "No active test found. Please check your history for pending or completed tests."}

    # 2. MAPPING CORRECTION: Map to the TestSession and related Practice model attributes
    tests_summary = []
    for t in active_tests:
        # Assuming Practice model has the 'title' field which you want to display
        # Note: If you want 'created_by' (Company name), you'll need to join or fetch it. 
        # I'll fetch it using the Practice's associated Company (which you haven't modeled yet).
        
        # *** Since the company relationship isn't directly on TestSession, we use a helper/join ***
        
        # For simplicity and correctness with your current model structure, we'll fetch the Company name 
        # using the User's Company ID, assuming the test is 'assigned' by the User's company (Recruiter).
        # A more robust solution involves a direct relationship from Practice/TestSession to Company.
        
        company_name = get_company_name(db, t.user.company_id) if t.user.company_id else "Unassigned Test"
        
        tests_summary.append({
            # The primary key column is session_id in TestSession
            "test_id": t.session_id, 
            "test_title": t.practice.title, # Assuming practice relationship is correctly configured
            "created_by": company_name, 
            "created_at": t.started_time, 
            # Note: TestSession doesn't have its own deadline; it uses Practice.deadline
            "deadline": t.practice.deadline, 
            # The score column is overall_points in TestSession
            "final_score": t.overall_points 
        })
    
    return tests_summary


@router.get("/completed")
def get_test_history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Retrieves a list of all test sessions assigned to the user (completed or pending).
    """
    
    # 1. QUERY CORRECTION: Use TestSession instead of StartedTest
    all_sessions = db.query(TestSession).filter(
        TestSession.user_id == user.id, TestSession.is_finished == True
    ).order_by(TestSession.started_time.desc()).all() # Use started_time for ordering

    if not all_sessions:
        return {"message": "The user hasn't finished any test"}

    # 2. MAPPING CORRECTION: Map to the TestSession and related Practice model attributes
    history_summaries = []
    for session in all_sessions: 
        company_name = get_company_name(db, session.user.company_id) if session.user.company_id else "Unassigned Test"

        history_summaries.append({
            "test_id": str(session.session_id),
            "assessment_name": session.practice.title,
            "date": session.started_time.strftime("%b %d, %Y"),
            "score": int(session.overall_points),
            "status_label": f"Passed ({int(session.overall_points)}%)" if session.overall_points >= 60 else "Failed",
            "action_url": f"/reports/{session.session_id}"
        })
    return history_summaries
