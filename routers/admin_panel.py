import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    Candidate,
    Company,
    Created_Vacancy,
    Practice, 
    PracticeAssignment, 
    Question, 
    QuestionHistory, 
    TestSession,
    User, 
    UserAnswer,
    Role
)
from routers.login import get_current_user
from schemas.user_schema import (
    AdminCandidateOut,
    AdminDashboardSummary,
    AdminTestSessionOut,
    AdminUserAnswerOut,
    AdminUserOut,
    AdminVacancyOut,
    AssignmentUpdate,
    CandidateStatusUpdate,
    CompanyOut,
    DifficultyUpdate,
    PracticeAssignmentOut,
    PracticeCreate,
    PracticeOut,
    PracticeUpdate,
    QuestionHistoryOut,
)

router = APIRouter(prefix="/admin", tags=["Admin"])

# --- SECURITY DEPENDENCY ---
def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in {Role.ADMIN, Role.SUPERADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not authorized. Admin access required."
        )
    return current_user


# --- ENDPOINTS ---

# Dashboard
@router.get("/dashboard/summary", response_model=AdminDashboardSummary)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    average_score = (
        db.query(func.avg(TestSession.overall_points))
        .filter(TestSession.is_finished == True)
        .scalar()
    )

    return {
        "total_users": db.query(User).count(),
        "total_candidates": db.query(Candidate).count(),
        "total_vacancies": db.query(Created_Vacancy).count(),
        "active_vacancies": db.query(Created_Vacancy).filter(Created_Vacancy.is_available == True).count(),
        "total_practices": db.query(Practice).count(),
        "active_practices": db.query(Practice).filter(Practice.is_valid == True).count(),
        "total_questions": db.query(Question).count(),
        "active_test_sessions": db.query(TestSession).filter(TestSession.is_finished == False).count(),
        "completed_test_sessions": db.query(TestSession).filter(TestSession.is_finished == True).count(),
        "average_test_score": int(average_score or 0),
    }


# Users and companies
@router.get("/users", response_model=List[AdminUserOut])
def list_users(
    role: Optional[Role] = None,
    search: Optional[str] = None,
    company_id: Optional[uuid.UUID] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    query = db.query(User)

    if role:
        query = query.filter(User.role == role)
    if company_id:
        query = query.filter(User.company_id == company_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(User.username.ilike(pattern), User.name.ilike(pattern), User.surname.ilike(pattern)))

    return query.order_by(User.username.asc()).offset(offset).limit(limit).all()


@router.get("/users/{user_id}", response_model=AdminUserOut)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/companies", response_model=List[CompanyOut])
def list_companies(
    search: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    query = db.query(Company)

    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Company.name.ilike(pattern), Company.email.ilike(pattern), Company.INN.ilike(pattern)))

    return query.order_by(Company.name.asc()).offset(offset).limit(limit).all()


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.get("/companies/{company_id}/users", response_model=List[AdminUserOut])
def list_company_users(
    company_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    return (
        db.query(User)
        .filter(User.company_id == company_id)
        .order_by(User.username.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/companies/{company_id}/vacancies", response_model=List[AdminVacancyOut])
def list_company_vacancies(
    company_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    return (
        db.query(Created_Vacancy)
        .filter(Created_Vacancy.company_id == company_id)
        .order_by(Created_Vacancy.start_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


# Vacancies and candidates
@router.get("/vacancies", response_model=List[AdminVacancyOut])
def list_vacancies(
    company_id: Optional[uuid.UUID] = None,
    is_available: Optional[bool] = None,
    search: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    query = db.query(Created_Vacancy)

    if company_id:
        query = query.filter(Created_Vacancy.company_id == company_id)
    if is_available is not None:
        query = query.filter(Created_Vacancy.is_available == is_available)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Created_Vacancy.job_name.ilike(pattern), Created_Vacancy.tag.ilike(pattern)))

    return query.order_by(Created_Vacancy.start_date.desc()).offset(offset).limit(limit).all()


@router.get("/vacancies/{vacancy_id}", response_model=AdminVacancyOut)
def get_vacancy(
    vacancy_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    vacancy = db.query(Created_Vacancy).filter(Created_Vacancy.id == vacancy_id).first()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    return vacancy


@router.get("/vacancies/{vacancy_id}/candidates", response_model=List[AdminCandidateOut])
def list_vacancy_candidates(
    vacancy_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    query = db.query(Candidate).filter(Candidate.vacancy_id == vacancy_id)

    if status_filter:
        query = query.filter(Candidate.status == status_filter)

    return query.order_by(Candidate.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/candidates", response_model=List[AdminCandidateOut])
def list_candidates(
    status_filter: Optional[str] = Query(None, alias="status"),
    vacancy_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    query = db.query(Candidate)

    if status_filter:
        query = query.filter(Candidate.status == status_filter)
    if vacancy_id:
        query = query.filter(Candidate.vacancy_id == vacancy_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Candidate.full_name.ilike(pattern), Candidate.skills.ilike(pattern)))

    return query.order_by(Candidate.created_at.desc()).offset(offset).limit(limit).all()


@router.patch("/candidates/{candidate_id}/status", response_model=AdminCandidateOut)
def update_candidate_status(
    candidate_id: uuid.UUID,
    update_data: CandidateStatusUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    candidate.status = update_data.status
    db.commit()
    db.refresh(candidate)
    return candidate


# Questions
@router.get("/questions")
def list_questions(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50, 
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)
):
    query = db.query(Question)

    if category:
        query = query.filter(Question.category == category)
    if search:
        query = query.filter(Question.text.ilike(f"%{search}%"))

    questions = query.order_by(Question.category.asc(), Question.difficulty_level.asc()).offset(offset).limit(limit).all()
    if not questions:
        return []
    return [
        {
            "id": q.id,
            "text": q.text,
            "category": q.category,
            "points": q.points,
            "difficulty_level": q.difficulty_level,
        }
        for q in questions
    ]


@router.get("/questions/{question_id}")
def get_question(
    question_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    return {
        "id": question.id,
        "text": question.text,
        "category": question.category,
        "options": question.options,
        "correct_answer": str(question.correct_answer),
        "difficulty_level": question.difficulty_level,
        "points": question.points,
    }


@router.patch("/questions/{question_id}/difficulty")
def update_question_difficulty(
    question_id: uuid.UUID,
    update_data: DifficultyUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    old_difficulty = question.difficulty_level
    question.difficulty_level = update_data.new_difficulty
    db.add(QuestionHistory(
        id=uuid.uuid4(),
        question_id=question.id,
        old_difficulty=old_difficulty,
        new_difficulty=update_data.new_difficulty,
        change_reason=update_data.change_reason,
        changed_by=admin_user.id,
    ))
    db.commit()
    db.refresh(question)

    return {
        "id": question.id,
        "old_difficulty": old_difficulty,
        "new_difficulty": question.difficulty_level,
        "change_reason": update_data.change_reason,
    }


@router.get("/questions/{question_id}/history", response_model=List[QuestionHistoryOut])
def list_question_history(
    question_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    return (
        db.query(QuestionHistory)
        .filter(QuestionHistory.question_id == question_id)
        .order_by(QuestionHistory.changed_at.desc())
        .all()
    )


# Practices and assignments
@router.get("/practices", response_model=List[PracticeOut])
def list_practices(
    is_valid: Optional[bool] = None,
    search: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    query = db.query(Practice)

    if is_valid is not None:
        query = query.filter(Practice.is_valid == is_valid)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Practice.title.ilike(pattern), Practice.description.ilike(pattern)))

    return query.order_by(Practice.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/practices/{practice_id}", response_model=PracticeOut)
def get_practice(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")
    return practice


@router.get("/practices/{practice_id}/questions")
def list_practice_questions(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")

    if not practice.question_ids:
        return []

    questions = db.query(Question).filter(Question.id.in_(practice.question_ids)).all()
    return [
        {
            "id": q.id,
            "text": q.text,
            "category": q.category,
            "difficulty_level": q.difficulty_level,
            "points": q.points,
        }
        for q in questions
    ]


@router.post("/practices")
def create_practice(
    practice_data: PracticeCreate,
    db: Session = Depends(get_db),
    admin_user = Depends(require_admin)
):
    new_practice = Practice(
        practice_id=uuid.uuid4(),
        title=practice_data.title,
        description=practice_data.description or "",
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


@router.patch("/practices/{practice_id}", response_model=PracticeOut)
def update_practice(
    practice_id: uuid.UUID,
    update_data: PracticeUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")

    for field, value in update_data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(practice, field, value)

    db.commit()
    db.refresh(practice)
    return practice


@router.get("/practices/{practice_id}/assignments", response_model=List[PracticeAssignmentOut])
def list_practice_assignments(
    practice_id: uuid.UUID,
    is_completed: Optional[bool] = None,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    query = db.query(PracticeAssignment).filter(PracticeAssignment.practice_id == practice_id)

    if is_completed is not None:
        query = query.filter(PracticeAssignment.is_completed == is_completed)

    return query.order_by(PracticeAssignment.assigned_at.desc()).all()


@router.patch("/practices/{practice_id}/assignments")
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


# Test sessions
@router.get("/test-sessions", response_model=List[AdminTestSessionOut])
def list_test_sessions(
    is_finished: Optional[bool] = None,
    user_id: Optional[uuid.UUID] = None,
    practice_id: Optional[uuid.UUID] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    query = db.query(TestSession)

    if is_finished is not None:
        query = query.filter(TestSession.is_finished == is_finished)
    if user_id:
        query = query.filter(TestSession.user_id == user_id)
    if practice_id:
        query = query.filter(TestSession.practice_id == practice_id)

    return query.order_by(TestSession.started_time.desc()).offset(offset).limit(limit).all()


@router.get("/test-sessions/{session_id}", response_model=AdminTestSessionOut)
def get_test_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    session = db.query(TestSession).filter(TestSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Test session not found")
    return session


@router.get("/test-sessions/{session_id}/answers", response_model=List[AdminUserAnswerOut])
def list_test_session_answers(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    return (
        db.query(UserAnswer)
        .filter(UserAnswer.session_id == session_id)
        .order_by(UserAnswer.id.asc())
        .all()
    )
