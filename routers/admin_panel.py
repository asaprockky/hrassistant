import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

# --- Adjust these imports to match your project structure ---
from database.database import get_db
# ADDED: Role import is needed for the admin check
from database.models import Practice, PracticeAssignment, Question, User, Role
from routers.login import get_current_user
from schemas.user_schema import AssignmentUpdate, PracticeCreate

router = APIRouter()

# --- SECURITY DEPENDENCY ---
# This was missing in your snippet!
def require_admin(current_user: User = Depends(get_current_user)):
    # Adjust "Role.ADMIN" if your Enum is named differently (e.g. Role.admin)
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not authorized. Admin access required."
        )
    return current_user

# --- ENDPOINTS ---

# 1. Search Questions (Admins Only)
@router.get("/questions/filter")
def get_questions_by_tag(
    category: str, 
    limit: int = 50, 
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)  # <--- Now valid because require_admin is defined above
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
        tags=practice_data.tags, # Add this line
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