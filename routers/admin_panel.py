import uuid
import secrets
import string
from datetime import datetime
from typing import List, Optional
from sqlalchemy import or_
from fastapi import Query
import math
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from passlib.context import CryptContext # Standard for password hashing

# --- Imports ---
from database.database import get_db
from database.models import Practice, PracticeAssignment, User, Role
from routers.login import get_current_user
from schemas.user_schema import CandidateCreate, CandidateCreatedResponse, AdvancedAssignmentUpdate, PaginatedUserResponse

router = APIRouter(prefix="/admin", tags=["Admin"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- SECURITY DEPENDENCY ---
def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not authorized. Admin access required."
        )
    return current_user

# --- HELPER FUNCTIONS ---
def generate_random_password(length=8):
    """Generates a secure random 8-character password."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))

def generate_unique_username(name: str, surname: str, db: Session):
    """Generates a unique username like john.doe.492"""
    base = f"{name.lower()}.{surname.lower()}"
    while True:
        suffix = secrets.randbelow(9000) + 1000 # Random 4 digit number
        username = f"{base}.{suffix}"
        exists = db.query(User).filter(User.username == username).first()
        if not exists:
            return username


# ==========================================
# 1. CANDIDATE CREATION API
# ==========================================
@router.post("/candidates", response_model=CandidateCreatedResponse)
def create_candidate(
    data: CandidateCreate,
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)
):
    """Creates a user automatically generating a unique username and password."""
    
    raw_password = generate_random_password()
    hashed_password = pwd_context.hash(raw_password)
    username = generate_unique_username(data.name, data.surname, db)

    new_user = User(
        id=uuid.uuid4(),
        username=username,
        password=hashed_password,
        role=Role.USER,
        name=data.name,
        surname=data.surname,
        age=data.age,
        email=data.email,
        group_name=data.group_name
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Return the unhashed password so the admin can give it to the candidate!
    return {
        "id": new_user.id,
        "username": new_user.username,
        "password": raw_password, 
        "group_name": new_user.group_name
    }


# ==========================================
# 2. ADVANCED ASSIGNMENT API (Groups + IDs)
# ==========================================
@router.patch("/practices/{practice_id}/assignments")
def manage_advanced_assignments(
    practice_id: uuid.UUID,
    update_data: AdvancedAssignmentUpdate,
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)
):
    """Assigns or removes a practice to specific users AND/OR entire groups."""
    
    practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")

    response_data = {"added": 0, "removed": 0}

    # --- PART A: REMOVALS ---
    # Find all users to remove (combining explicit IDs + Group members)
    users_to_remove_query = db.query(User.id).filter(
        or_(
            User.id.in_(update_data.remove_user_ids),
            User.group_name.in_(update_data.remove_groups) if update_data.remove_groups else False
        )
    )
    remove_ids = [row[0] for row in users_to_remove_query.all()]

    if remove_ids:
        deleted_count = db.query(PracticeAssignment).filter(
            PracticeAssignment.practice_id == practice_id,
            PracticeAssignment.user_id.in_(remove_ids)
        ).delete(synchronize_session=False)
        response_data["removed"] = deleted_count

    # --- PART B: ADDITIONS ---
    # Find all users to add (combining explicit IDs + Group members)
    users_to_add_query = db.query(User.id).filter(
        or_(
            User.id.in_(update_data.add_user_ids),
            User.group_name.in_(update_data.add_groups) if update_data.add_groups else False
        )
    )
    # Using a set removes duplicate target IDs instantly
    target_add_ids = {row[0] for row in users_to_add_query.all()} 

    if target_add_ids:
        # Fetch current assignments to avoid Duplicate Key Errors
        existing_assignments = db.query(PracticeAssignment.user_id).filter(
            PracticeAssignment.practice_id == practice_id,
            PracticeAssignment.user_id.in_(target_add_ids)
        ).all()
        existing_ids = {row[0] for row in existing_assignments}

        # Calculate only the users who don't already have the assignment
        final_ids_to_add = target_add_ids - existing_ids

        new_assignments = [
            PracticeAssignment(
                assignment_id=uuid.uuid4(),
                practice_id=practice_id,
                user_id=u_id,
                assigned_at=datetime.utcnow(),
                is_completed=False
            ) for u_id in final_ids_to_add
        ]

        if new_assignments:
            db.add_all(new_assignments)
            response_data["added"] = len(new_assignments)

    db.commit()
    
    return {"message": "Assignments successfully updated", "details": response_data}



@router.get("/users/search", response_model=PaginatedUserResponse)
def search_users(
    query: Optional[str] = Query(None, description="Search by name, surname, or username"),
    group: Optional[str] = Query(None, description="Filter by exact group name"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)
):
    """
    Search and paginate candidates for assignment purposes.
    """
    # 1. Base query: Only fetch regular users (not other admins)
    base_query = db.query(User).filter(User.role == Role.USER)

    # 2. Apply Text Search (Name, Surname, or Username)
    if query:
        search_term = f"%{query}%"
        base_query = base_query.filter(
            or_(
                User.name.ilike(search_term),
                User.surname.ilike(search_term),
                User.username.ilike(search_term)
            )
        )

    # 3. Apply Group Filter
    if group:
        base_query = base_query.filter(User.group_name == group)

    # 4. Calculate Pagination totals
    total_items = base_query.count()
    total_pages = math.ceil(total_items / size) if total_items > 0 else 1

    # 5. Fetch the specific page of results
    # .offset() skips the previous pages, .limit() grabs the current page
    users = base_query.order_by(User.surname.asc(), User.name.asc())\
                      .offset((page - 1) * size)\
                      .limit(size)\
                      .all()

    return {
        "items": users,
        "total_items": total_items,
        "page": page,
        "size": size,
        "total_pages": total_pages
    }