import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

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


def _user_display_name(user: Optional[User]) -> Optional[str]:
    if not user:
        return None
    full_name = " ".join(part for part in [user.name, user.surname] if part).strip()
    return full_name or user.username


def _option_text(question: Optional[Question], option_id) -> Optional[str]:
    if not question or option_id is None:
        return None

    option_id_text = str(option_id)
    options = question.options or []

    if isinstance(options, dict):
        for key, value in options.items():
            if str(key) == option_id_text:
                return value.get("text") if isinstance(value, dict) else str(value)
            if isinstance(value, dict) and str(value.get("id")) == option_id_text:
                return value.get("text")
        return None

    for option in options:
        if isinstance(option, dict) and str(option.get("id")) == option_id_text:
            return option.get("text")

    return None


def _admin_user_out(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "name": user.name,
        "surname": user.surname,
        "age": user.age,
        "email": user.email,
        "company_id": user.company_id,
        "company_name": user.company.name if user.company else None,
    }


def _admin_vacancy_out(vacancy: Created_Vacancy) -> dict:
    return {
        "id": vacancy.id,
        "job_name": vacancy.job_name,
        "job_description": vacancy.job_description,
        "tag": vacancy.tag,
        "start_date": vacancy.start_date,
        "end_date": vacancy.end_date,
        "company_id": vacancy.company_id,
        "company_name": vacancy.company.name if vacancy.company else None,
        "candidate_count": vacancy.candidate_count,
        "is_available": vacancy.is_available,
    }


def _admin_candidate_out(candidate: Candidate) -> dict:
    vacancy = candidate.vacancy
    company = vacancy.company if vacancy else None

    return {
        "id": candidate.id,
        "user_id": candidate.user_id,
        "user_name": _user_display_name(candidate.user),
        "user_username": candidate.user.username if candidate.user else None,
        "vacancy_id": candidate.vacancy_id,
        "position_title": vacancy.job_name if vacancy else None,
        "company_name": company.name if company else None,
        "full_name": candidate.full_name,
        "status": candidate.status,
        "resume_loc": candidate.resume_loc,
        "ai_score": candidate.ai_score,
        "created_at": candidate.created_at,
        "education": candidate.education,
        "experience": candidate.experience,
        "skills": candidate.skills,
    }


def _question_text_map(db: Session, question_ids: List[uuid.UUID]) -> Dict[str, str]:
    unique_question_ids = []
    seen_question_ids = set()
    for question_id in question_ids:
        if question_id is None:
            continue
        question_id_text = str(question_id)
        if question_id_text not in seen_question_ids:
            seen_question_ids.add(question_id_text)
            unique_question_ids.append(question_id)

    if not unique_question_ids:
        return {}

    questions = db.query(Question).filter(Question.id.in_(unique_question_ids)).all()
    return {str(question.id): question.text for question in questions}


def _admin_practice_out(practice: Practice, question_text_by_id: Dict[str, str]) -> dict:
    question_texts = [
        question_text_by_id[str(question_id)]
        for question_id in (practice.question_ids or [])
        if str(question_id) in question_text_by_id
    ]

    return {
        "practice_id": practice.practice_id,
        "title": practice.title,
        "description": practice.description,
        "duration_minutes": practice.duration_minutes,
        "deadline": practice.deadline,
        "question_ids": practice.question_ids,
        "question_texts": question_texts,
        "tags": practice.tags,
        "is_valid": practice.is_valid,
        "created_at": practice.created_at,
    }


def _admin_practices_out(db: Session, practices: List[Practice]) -> List[dict]:
    question_ids = [
        question_id
        for practice in practices
        for question_id in (practice.question_ids or [])
    ]
    question_text_by_id = _question_text_map(db, question_ids)
    return [_admin_practice_out(practice, question_text_by_id) for practice in practices]


def _admin_assignment_out(
    assignment: PracticeAssignment,
    practice_by_id: Dict[str, Practice],
    user_by_id: Dict[str, User],
) -> dict:
    practice = practice_by_id.get(str(assignment.practice_id))
    user = user_by_id.get(str(assignment.user_id))

    return {
        "assignment_id": assignment.assignment_id,
        "practice_id": assignment.practice_id,
        "practice_title": practice.title if practice else None,
        "user_id": assignment.user_id,
        "user_name": _user_display_name(user),
        "user_username": user.username if user else None,
        "assigned_at": assignment.assigned_at,
        "is_completed": assignment.is_completed,
        "completed_at": assignment.completed_at,
    }


def _admin_assignments_out(db: Session, assignments: List[PracticeAssignment]) -> List[dict]:
    practice_ids = [assignment.practice_id for assignment in assignments]
    user_ids = [assignment.user_id for assignment in assignments]

    practices = db.query(Practice).filter(Practice.practice_id.in_(practice_ids)).all() if practice_ids else []
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []

    practice_by_id = {str(practice.practice_id): practice for practice in practices}
    user_by_id = {str(user.id): user for user in users}

    return [
        _admin_assignment_out(assignment, practice_by_id, user_by_id)
        for assignment in assignments
    ]


def _admin_test_session_out(session: TestSession) -> dict:
    return {
        "session_id": session.session_id,
        "practice_id": session.practice_id,
        "practice_title": session.practice.title if session.practice else None,
        "user_id": session.user_id,
        "user_name": _user_display_name(session.user),
        "user_username": session.user.username if session.user else None,
        "overall_points": session.overall_points,
        "is_finished": session.is_finished,
        "started_time": session.started_time,
    }


def _admin_answer_out(answer: UserAnswer, question_by_id: Dict[str, Question]) -> dict:
    question = question_by_id.get(str(answer.question_id))

    return {
        "id": answer.id,
        "session_id": answer.session_id,
        "question_id": answer.question_id,
        "question_text": question.text if question else None,
        "user_answer": answer.user_answer,
        "user_answer_text": _option_text(question, answer.user_answer),
        "correct_answer_text": _option_text(question, question.correct_answer) if question else None,
        "is_correct": answer.is_correct,
        "points_awarded": answer.points_awarded,
        "time_spent": answer.time_spent,
    }


def _admin_question_history_out(history: QuestionHistory, changed_by_user: Optional[User]) -> dict:
    return {
        "id": history.id,
        "question_id": history.question_id,
        "question_text": history.question.text if history.question else None,
        "old_difficulty": history.old_difficulty,
        "new_difficulty": history.new_difficulty,
        "change_reason": history.change_reason,
        "changed_at": history.changed_at,
        "changed_by": history.changed_by,
        "changed_by_name": _user_display_name(changed_by_user),
        "changed_by_username": changed_by_user.username if changed_by_user else None,
    }


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
    query = db.query(User).options(joinedload(User.company))

    if role:
        query = query.filter(User.role == role)
    if company_id:
        query = query.filter(User.company_id == company_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(User.username.ilike(pattern), User.name.ilike(pattern), User.surname.ilike(pattern)))

    users = query.order_by(User.username.asc()).offset(offset).limit(limit).all()
    return [_admin_user_out(user) for user in users]


@router.get("/users/{user_id}", response_model=AdminUserOut)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    user = (
        db.query(User)
        .options(joinedload(User.company))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _admin_user_out(user)


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
    users = (
        db.query(User)
        .options(joinedload(User.company))
        .filter(User.company_id == company_id)
        .order_by(User.username.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_admin_user_out(user) for user in users]


@router.get("/companies/{company_id}/vacancies", response_model=List[AdminVacancyOut])
def list_company_vacancies(
    company_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    vacancies = (
        db.query(Created_Vacancy)
        .options(joinedload(Created_Vacancy.company))
        .filter(Created_Vacancy.company_id == company_id)
        .order_by(Created_Vacancy.start_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_admin_vacancy_out(vacancy) for vacancy in vacancies]


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
    query = db.query(Created_Vacancy).options(joinedload(Created_Vacancy.company))

    if company_id:
        query = query.filter(Created_Vacancy.company_id == company_id)
    if is_available is not None:
        query = query.filter(Created_Vacancy.is_available == is_available)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Created_Vacancy.job_name.ilike(pattern), Created_Vacancy.tag.ilike(pattern)))

    vacancies = query.order_by(Created_Vacancy.start_date.desc()).offset(offset).limit(limit).all()
    return [_admin_vacancy_out(vacancy) for vacancy in vacancies]


@router.get("/vacancies/{vacancy_id}", response_model=AdminVacancyOut)
def get_vacancy(
    vacancy_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    vacancy = (
        db.query(Created_Vacancy)
        .options(joinedload(Created_Vacancy.company))
        .filter(Created_Vacancy.id == vacancy_id)
        .first()
    )
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    return _admin_vacancy_out(vacancy)


@router.get("/vacancies/{vacancy_id}/candidates", response_model=List[AdminCandidateOut])
def list_vacancy_candidates(
    vacancy_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    query = (
        db.query(Candidate)
        .options(
            joinedload(Candidate.user),
            joinedload(Candidate.vacancy).joinedload(Created_Vacancy.company),
        )
        .filter(Candidate.vacancy_id == vacancy_id)
    )

    if status_filter:
        query = query.filter(Candidate.status == status_filter)

    candidates = query.order_by(Candidate.created_at.desc()).offset(offset).limit(limit).all()
    return [_admin_candidate_out(candidate) for candidate in candidates]


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
    query = db.query(Candidate).options(
        joinedload(Candidate.user),
        joinedload(Candidate.vacancy).joinedload(Created_Vacancy.company),
    )

    if status_filter:
        query = query.filter(Candidate.status == status_filter)
    if vacancy_id:
        query = query.filter(Candidate.vacancy_id == vacancy_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Candidate.full_name.ilike(pattern), Candidate.skills.ilike(pattern)))

    candidates = query.order_by(Candidate.created_at.desc()).offset(offset).limit(limit).all()
    return [_admin_candidate_out(candidate) for candidate in candidates]


@router.patch("/candidates/{candidate_id}/status", response_model=AdminCandidateOut)
def update_candidate_status(
    candidate_id: uuid.UUID,
    update_data: CandidateStatusUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    candidate = (
        db.query(Candidate)
        .options(
            joinedload(Candidate.user),
            joinedload(Candidate.vacancy).joinedload(Created_Vacancy.company),
        )
        .filter(Candidate.id == candidate_id)
        .first()
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    candidate.status = update_data.status
    db.commit()
    db.refresh(candidate)
    return _admin_candidate_out(candidate)


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
        "correct_answer_text": _option_text(question, question.correct_answer),
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
    history_items = (
        db.query(QuestionHistory)
        .options(joinedload(QuestionHistory.question))
        .filter(QuestionHistory.question_id == question_id)
        .order_by(QuestionHistory.changed_at.desc())
        .all()
    )
    changed_by_ids = [history.changed_by for history in history_items if history.changed_by]
    changed_by_users = (
        db.query(User).filter(User.id.in_(changed_by_ids)).all()
        if changed_by_ids
        else []
    )
    changed_by_user_by_id = {str(user.id): user for user in changed_by_users}

    return [
        _admin_question_history_out(
            history,
            changed_by_user_by_id.get(str(history.changed_by)),
        )
        for history in history_items
    ]


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

    practices = query.order_by(Practice.created_at.desc()).offset(offset).limit(limit).all()
    return _admin_practices_out(db, practices)


@router.get("/practices/{practice_id}", response_model=PracticeOut)
def get_practice(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")
    return _admin_practices_out(db, [practice])[0]


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
    return _admin_practices_out(db, [practice])[0]


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

    assignments = query.order_by(PracticeAssignment.assigned_at.desc()).all()
    return _admin_assignments_out(db, assignments)


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
    query = db.query(TestSession).options(
        joinedload(TestSession.practice),
        joinedload(TestSession.user),
    )

    if is_finished is not None:
        query = query.filter(TestSession.is_finished == is_finished)
    if user_id:
        query = query.filter(TestSession.user_id == user_id)
    if practice_id:
        query = query.filter(TestSession.practice_id == practice_id)

    sessions = query.order_by(TestSession.started_time.desc()).offset(offset).limit(limit).all()
    return [_admin_test_session_out(session) for session in sessions]


@router.get("/test-sessions/{session_id}", response_model=AdminTestSessionOut)
def get_test_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    session = (
        db.query(TestSession)
        .options(
            joinedload(TestSession.practice),
            joinedload(TestSession.user),
        )
        .filter(TestSession.session_id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Test session not found")
    return _admin_test_session_out(session)


@router.get("/test-sessions/{session_id}/answers", response_model=List[AdminUserAnswerOut])
def list_test_session_answers(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    answers = (
        db.query(UserAnswer)
        .filter(UserAnswer.session_id == session_id)
        .order_by(UserAnswer.id.asc())
        .all()
    )
    question_ids = [answer.question_id for answer in answers if answer.question_id]
    questions = (
        db.query(Question).filter(Question.id.in_(question_ids)).all()
        if question_ids
        else []
    )
    question_by_id = {str(question.id): question for question in questions}

    return [_admin_answer_out(answer, question_by_id) for answer in answers]
