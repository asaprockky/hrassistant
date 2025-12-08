from datetime import datetime
from fastapi import APIRouter, Depends
from database.database import get_db
from sqlalchemy.orm import Session
from database.models import User, UserProfile, StartedTest
from routers.login import get_current_user
router = APIRouter()


    
@router.get("/tests/active")
def get_active_tests(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    active_tests = db.query(StartedTest).join(StartedTest.owner_company).filter(
        StartedTest.user_id == user.id,
        StartedTest.is_active == True
    ).all()

    if not active_tests:
        return {
            "is_active": False,
            "message": "No active test found. Please check your history for pending or completed tests."
        }

    # Return list of summaries
    tests_summary = [
        {
            "test_id": t.test_id,
            "created_by": t.owner_company.name,
            "created_at": t.created_at,
            "deadline": t.deadline
        } for t in active_tests
    ]

    return {
        "is_active": True,
        "tests": tests_summary
    }

@router.get("/tests/passed")
def get_test_history(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Retrieves a list of all tests assigned to the user (including completed, pending, or expired).
    """
    # Query for all tests for the user, ordered by creation date
    all_tests = db.query(StartedTest).join(StartedTest.owner_company).filter(
        StartedTest.user_id == user.id,
    ).order_by(StartedTest.created_at.desc()).all()

    if not all_tests:
        return {"message": "No tests have been assigned to this user."}

    # Map the SQLAlchemy objects to a list of history summaries
    history_summaries = []
    for test in all_tests:       
        history_summaries.append({
            "test_id": test.test_id,
            "created_by": test.owner_company.name,
            "created_at": test.created_at,
            "deadline": test.deadline,
            "final_score": test.current_score
        })

    return history_summaries


