from datetime import datetime
from fastapi import APIRouter, Depends
from database.database import get_db
from sqlalchemy.orm import Session
from database.models import User, UserProfile, StartedTest
from routers.login import get_current_user
router = APIRouter()


    

@router.get("tests/active")
def get_active_test(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Retrieves the details of the single currently active/in-progress test for the user.
    """
    # Query for the active test, using join to load Company data efficiently
    active_test = db.query(StartedTest).join(StartedTest.owner_company).filter(
        StartedTest.user_id == user.id,
        StartedTest.is_active == True
    ).first()

    if active_test:
        test_summary = {
            "test_id": active_test.test_id,
            "created_by": active_test.owner_company.name,
            "created_at": active_test.created_at,
            "deadline": active_test.deadline
        }
        return test_summary
    else:
        # Return a simple object indicating no active test
        return {
            "is_active": False,
            "message": "No active test found. Please check your history for pending or completed tests."
        }
    

@router.get("tests/passed")
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
        # Determine a more descriptive status
        if test.is_active:
            status = "In Progress"
        elif test.deadline and test.deadline < datetime.now():
            status = "Expired"
        else:
            # You might need a way to check if it was completed vs. just pending
            # For now, we'll mark non-active, non-expired tests as 'Pending/Completed'
            status = "Pending/Completed" 
        
        history_summaries.append({
            "test_id": test.test_id,
            "status": status,
            "created_by": test.owner_company.name,
            "created_at": test.created_at,
            "deadline": test.deadline,
            "final_score": test.current_score if status == "Completed" else None # Assuming final score is in current_score
        })

    return history_summaries


