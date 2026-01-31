import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# --- Project Imports ---
from database.database import get_db
# Added QuestionHistory to imports
from database.models import (
    Practice, 
    PracticeAssignment, 
    Question, 
    QuestionHistory, 
    User, 
    Role
)
from routers.login import get_current_user
# Added new schemas for Questions and History
from schemas.user_schema import (
    AssignmentUpdate, 
    PracticeCreate, 
    QuestionOut, 
    QuestionHistoryOut, 
    DifficultyUpdate
)

router = APIRouter()

# --- SECURITY DEPENDENCY ---
def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not authorized. Admin access required."
        )
    return current_user


# --- ENDPOINTS ---

# 1. Search Questions by Category (Admins Only)
@router.get("/questions/filter")
def get_questions_by_tag(
    category: str, 
    limit: int = 50, 
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)
):
    questions = db.query(Question).filter(Question.category == category).limit(limit).all()
    if not questions:
        return []
    return [{"id": q.id, "text": q.text, "category": q.category, "points": q.points} for q in questions]


# 2. Create Practice (Admins Only)
@router.post("/testing/create-practice")
def create_practice(
    practice_data: PracticeCreate,
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)
):
    new_practice = Practice(
        practice_id=uuid.uuid4(),
        title=practice_data.title,
        description=practice_data.description,
        duration_minutes=practice_data.duration_minutes,
        question_ids=practice_data.question_ids, 
        tags=practice_data.tags,
        is_valid=True,
        deadline=practice_data.deadline,
        created_at=datetime.utcnow()
    )
    
    db.add(new_practice)
    db.commit()
    db.refresh(new_practice)
    
    return {
        "message": "Practice created successfully", 
        "practice_id": new_practice.practice_id
    }


# 3. Manage Assignments (Admins Only)
@router.patch("/testing/manage-assignments/{practice_id}")
def manage_assignments(
    practice_id: uuid.UUID,
    update_data: AssignmentUpdate,
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)
):
    practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")

    response_data = {"added": 0, "removed": 0}

    # Remove Users
    if update_data.remove_user_ids:
        delete_query = db.query(PracticeAssignment).filter(
            PracticeAssignment.practice_id == practice_id,
            PracticeAssignment.user_id.in_(update_data.remove_user_ids)
        )
        deleted_count = delete_query.delete(synchronize_session=False)
        response_data["removed"] = deleted_count

    # Add Users
    if update_data.add_user_ids:
        new_assignments = []
        for user_id in update_data.add_user_ids:
            # Check duplicate assignment
            exists = db.query(PracticeAssignment).filter(
                PracticeAssignment.practice_id == practice_id,
                PracticeAssignment.user_id == user_id
            ).first()
            
            if not exists:
                new_assignments.append(PracticeAssignment(
                    assignment_id=uuid.uuid4(),
                    practice_id=practice_id,
                    user_id=user_id,
                    assigned_at=datetime.utcnow()
                ))
        
        if new_assignments:
            db.add_all(new_assignments)
            response_data["added"] = len(new_assignments)

    db.commit()
    
    return {"message": "Assignments updated", "details": response_data}


# 4. List All Questions Detailed (Admins Only)
@router.get("/questions/all", response_model=List[QuestionOut])
def get_all_questions_detailed(
    skip: int = 0, 
    limit: int = 100, 
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)
):
    """
    Returns a full list of questions including options and difficulty.
    """
    query = db.query(Question)
    if category:
        query = query.filter(Question.category == category)
    
    return query.offset(skip).limit(limit).all()


# 5. Get Question History Log (Admins Only)
@router.get("/questions/{question_id}/history", response_model=List[QuestionHistoryOut])
def get_question_history(
    question_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)
):
    """
    Shows the history of difficulty changes/edits for a specific question.
    """
    history = db.query(QuestionHistory).filter(
        QuestionHistory.question_id == question_id
    ).order_by(QuestionHistory.changed_at.desc()).all()
    
    if not history:
        # Return empty list instead of 404 if no history exists yet
        return []
        
    return history


# 6. Manual Difficulty Adjustment (Admins Only)
@router.patch("/questions/{question_id}/update-difficulty")
def update_question_difficulty(
    question_id: uuid.UUID,
    update_data: DifficultyUpdate,
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)
):
    """
    Updates the difficulty of a question and creates a history log entry.
    """
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Create the history record
    history_log = QuestionHistory(
        id=uuid.uuid4(),
        question_id=question.id,
        old_difficulty=question.difficulty_level,
        new_difficulty=update_data.new_difficulty,
        change_reason=update_data.change_reason,
        changed_at=datetime.utcnow(),
        changed_by=admin_user.id
    )

    # Apply update to the actual Question
    question.difficulty_level = update_data.new_difficulty
    
    db.add(history_log)
    db.commit()
    db.refresh(question)

    return {
        "message": "Difficulty updated successfully",
        "question_id": question.id,
        "new_difficulty": question.difficulty_level
    }