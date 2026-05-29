import secrets
import string
import uuid
from datetime import date, datetime
from html import escape
from typing import Iterable, List, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from passlib.context import CryptContext
from sqlalchemy import case, func, literal, or_
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
    Role,
    SessionEvent,
    TestSession,
    TestSessionMeta,
    User,
    UserAnswer,
)
from routers.login import get_current_user
from schemas.user_schema import (
    AdminActivityItem,
    AdminActivityResponse,
    AdminBulkUserCreate,
    AdminBulkUserCreateResponse,
    AdminCandidateCreate,
    AdminCandidateOut,
    AdminCandidateUpdate,
    AdminDashboardSummary,
    AdminDeleteResult,
    AdminGroupStats,
    AdminGroupStatsResponse,
    AdminPagedAnswers,
    AdminPagedAssignments,
    AdminPagedCandidates,
    AdminPagedCompanies,
    AdminPagedPractices,
    AdminPagedQuestionHistory,
    AdminPagedQuestions,
    AdminPagedTestSessions,
    AdminPagedUsers,
    AdminPagedVacancies,
    AdminQuestionDifficultyResult,
    AdminStudentStatsResponse,
    AdminTestSessionOut,
    AdminUserAnswerOut,
    AdminUserCreate,
    AdminUserCreatedOut,
    AdminUserDetail,
    AdminUserOut,
    AdminUserPasswordReset,
    AdminUserPasswordResetResult,
    AdminUserSearchResponse,
    AdminUserUpdate,
    AdminVacancyCreate,
    AdminVacancyDetail,
    AdminVacancyOut,
    AdminVacancyUpdate,
    AdvancedAssignmentUpdate,
    CandidateStatusUpdate,
    CompanyCreate,
    CompanyDetail,
    CompanyOut,
    CompanyRef,
    CompanyUpdate,
    DifficultyUpdate,
    PracticeAssignmentOut,
    PracticeAssignmentResult,
    PracticeCreate,
    PracticeDetail,
    PracticeInvitationRequest,
    PracticeInvitationResult,
    PracticeOut,
    PracticeRef,
    PracticeUpdate,
    QuestionCreate,
    QuestionHistoryOut,
    QuestionOptionCreate,
    QuestionOut,
    QuestionRef,
    QuestionUpdate,
    SimpleAssignmentCreate,
    SimpleAssignmentOut,
    UserRef,
    VacancyRef,
)
from utils.mailer import EmailDeliveryError, send_email
from utils.status_notifications import notify_candidate_status_change


router = APIRouter(prefix="/admin", tags=["Admin"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in {Role.ADMIN, Role.SUPERADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized. Admin access required.",
        )
    return current_user


def hash_password(password: str) -> str:
    return pwd_context.hash(password.encode("utf-8")[:72])


def generate_random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _clean_username_part(value: str) -> str:
    cleaned = "".join(ch.lower() for ch in value if ch.isalnum())
    return cleaned or "user"


def generate_unique_username(
    name: str,
    surname: str,
    db: Session,
    reserved: Optional[set[str]] = None,
) -> str:
    reserved = reserved or set()
    base = f"{_clean_username_part(name)}.{_clean_username_part(surname)}"
    base = base[:24].strip(".") or "student"
    candidate = base
    counter = 1

    while candidate in reserved or db.query(User.id).filter(User.username == candidate).first():
        suffix = str(counter)
        candidate = f"{base[: 30 - len(suffix)]}{suffix}"
        counter += 1

    reserved.add(candidate)
    return candidate


def dedupe_username(
    base: str,
    db: Session,
    reserved: Optional[set[str]] = None,
) -> str:
    """Return a unique username derived from an explicitly-supplied `base`.

    Used by bulk/Excel import (cross-cutting requirement): a duplicate
    explicitly-supplied username is auto-renamed (john.doe -> john.doe1)
    instead of hard-failing the row.
    """
    reserved = reserved or set()
    base = (base or "").strip()[:30] or "student"
    candidate = base
    counter = 1
    while candidate in reserved or db.query(User.id).filter(User.username == candidate).first():
        suffix = str(counter)
        candidate = f"{base[: 30 - len(suffix)]}{suffix}"
        counter += 1
    reserved.add(candidate)
    return candidate


def apply_admin_user_scope(query, admin_user: User):
    if admin_user.role == Role.SUPERADMIN or not admin_user.company_id:
        return query
    return query.filter(User.company_id == admin_user.company_id)


def apply_admin_vacancy_scope(query, admin_user: User):
    if admin_user.role == Role.SUPERADMIN or not admin_user.company_id:
        return query
    return query.filter(Created_Vacancy.company_id == admin_user.company_id)


def ensure_user_visible_to_admin(user: User, admin_user: User) -> None:
    if admin_user.role == Role.SUPERADMIN or not admin_user.company_id:
        return
    if user.company_id != admin_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is outside this admin's company scope.",
        )


def ensure_role_can_be_created(role: Role, admin_user: User) -> None:
    if admin_user.role == Role.SUPERADMIN:
        return
    if role != Role.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins can only create student/user accounts.",
        )


def resolve_company_id(
    requested_company_id: Optional[uuid.UUID],
    admin_user: User,
) -> Optional[uuid.UUID]:
    if admin_user.role == Role.SUPERADMIN:
        return requested_company_id or admin_user.company_id

    if requested_company_id and requested_company_id != admin_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins can only create records inside their own company.",
        )

    return admin_user.company_id


def get_practice_or_404(db: Session, practice_id: uuid.UUID) -> Practice:
    practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")
    return practice


def validate_question_ids(db: Session, question_ids: Sequence[uuid.UUID]) -> None:
    if not question_ids:
        raise HTTPException(status_code=400, detail="A practice needs at least one question.")

    existing_ids = {
        row[0]
        for row in db.query(Question.id).filter(Question.id.in_(question_ids)).all()
    }
    missing_ids = [str(q_id) for q_id in question_ids if q_id not in existing_ids]
    if missing_ids:
        raise HTTPException(
            status_code=400,
            detail={"message": "Some questions do not exist.", "missing_question_ids": missing_ids},
        )


def normalize_question_options(options: List[QuestionOptionCreate]) -> tuple[list[dict], list[uuid.UUID]]:
    normalized = []
    option_ids = []
    seen = set()

    for option in options:
        text = option.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Question option text cannot be empty.")

        option_id = option.id or uuid.uuid4()
        if option_id in seen:
            raise HTTPException(status_code=400, detail="Question option IDs must be unique.")

        seen.add(option_id)
        option_ids.append(option_id)
        normalized.append({"id": str(option_id), "text": text})

    return normalized, option_ids


def resolve_correct_answer(
    option_ids: Sequence[uuid.UUID],
    correct_answer: Optional[uuid.UUID],
    correct_option_index: Optional[int],
    existing_correct_answer: Optional[uuid.UUID] = None,
) -> uuid.UUID:
    if correct_answer and correct_option_index is not None:
        raise HTTPException(
            status_code=400,
            detail="Use either correct_answer or correct_option_index, not both.",
        )

    if correct_answer:
        if correct_answer not in option_ids:
            raise HTTPException(status_code=400, detail="correct_answer must match one option ID.")
        return correct_answer

    if correct_option_index is not None:
        if correct_option_index >= len(option_ids):
            raise HTTPException(status_code=400, detail="correct_option_index is out of range.")
        return option_ids[correct_option_index]

    if existing_correct_answer and existing_correct_answer in option_ids:
        return existing_correct_answer

    raise HTTPException(
        status_code=400,
        detail="Provide a correct_answer or correct_option_index for these options.",
    )


def query_users_by_ids_or_groups(
    db: Session,
    admin_user: User,
    user_ids: Sequence[uuid.UUID],
    groups: Sequence[str],
):
    filters = []
    if user_ids:
        filters.append(User.id.in_(user_ids))
    if groups:
        filters.append(User.group_name.in_(groups))
    if not filters:
        return []

    query = db.query(User).filter(or_(*filters))
    return apply_admin_user_scope(query, admin_user).all()


def create_assignments(
    db: Session,
    practice_id: uuid.UUID,
    user_ids: Sequence[uuid.UUID],
) -> tuple[list[uuid.UUID], set[uuid.UUID]]:
    if not user_ids:
        return [], set()

    existing_ids = {
        row[0]
        for row in db.query(PracticeAssignment.user_id)
        .filter(
            PracticeAssignment.practice_id == practice_id,
            PracticeAssignment.user_id.in_(user_ids),
        )
        .all()
    }
    ids_to_add = [user_id for user_id in user_ids if user_id not in existing_ids]

    for user_id in ids_to_add:
        db.add(
            PracticeAssignment(
                assignment_id=uuid.uuid4(),
                practice_id=practice_id,
                user_id=user_id,
                assigned_at=datetime.utcnow(),
                is_completed=False,
            )
        )

    return ids_to_add, existing_ids


def build_practice_link(base_url: Optional[str], practice_id: uuid.UUID) -> Optional[str]:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/{practice_id}"


def send_practice_invitation(
    user: User,
    practice: Practice,
    raw_password: Optional[str] = None,
    frontend_test_base_url: Optional[str] = None,
    message: Optional[str] = None,
) -> None:
    if not user.email:
        raise EmailDeliveryError(f"{user.username} has no email address.")

    link = build_practice_link(frontend_test_base_url, practice.practice_id)
    deadline = practice.deadline.isoformat() if practice.deadline else "No deadline"
    password_line = f"\nPassword: {raw_password}" if raw_password else ""
    link_line = f"\nOpen the test: {link}" if link else ""
    custom_line = f"\n\n{message}" if message else ""

    plain_text = (
        f"Hello {user.name},\n\n"
        f"You have been invited to take this assessment: {practice.title}.\n"
        f"Username: {user.username}"
        f"{password_line}\n"
        f"Deadline: {deadline}"
        f"{link_line}"
        f"{custom_line}\n\n"
        "Only invited users can open this assessment."
    )

    password_html = (
        f"<p><strong>Password:</strong> {escape(raw_password)}</p>" if raw_password else ""
    )
    link_html = (
        f'<p><a href="{escape(link)}">Open assessment</a></p>' if link else ""
    )
    custom_html = f"<p>{escape(message)}</p>" if message else ""
    html = f"""
    <html>
      <body>
        <p>Hello {escape(user.name)},</p>
        <p>You have been invited to take this assessment: <strong>{escape(practice.title)}</strong>.</p>
        <p><strong>Username:</strong> {escape(user.username)}</p>
        {password_html}
        <p><strong>Deadline:</strong> {escape(deadline)}</p>
        {link_html}
        {custom_html}
        <p>Only invited users can open this assessment.</p>
      </body>
    </html>
    """

    send_email(
        to_email=user.email,
        subject=f"Assessment invitation: {practice.title}",
        plain_text=plain_text,
        html=html,
    )


def serialize_created_user(
    user: User,
    raw_password: Optional[str],
    practice_id: Optional[uuid.UUID],
    already_existed: bool = False,
) -> AdminUserCreatedOut:
    return AdminUserCreatedOut(
        id=user.id,
        username=user.username,
        password=raw_password,
        email=user.email,
        group_name=user.group_name,
        assigned_practice_id=practice_id,
        already_existed=already_existed,
    )


# ---------------------------------------------------------------------------
# Serializer helpers -- keep responses enriched (no bare IDs) without
# triggering extra DB round trips. Callers must eager-load the relations
# referenced below or the helpers will silently leave them as null.
# ---------------------------------------------------------------------------


def _company_ref(company: Optional[Company]) -> Optional[CompanyRef]:
    if not company:
        return None
    return CompanyRef.model_validate(company)


def _user_ref(user: Optional[User]) -> Optional[UserRef]:
    if not user:
        return None
    return UserRef.model_validate(user)


def _vacancy_ref(vacancy: Optional[Created_Vacancy]) -> Optional[VacancyRef]:
    if not vacancy:
        return None
    return VacancyRef.model_validate(vacancy)


def _practice_ref(practice: Optional[Practice]) -> Optional[PracticeRef]:
    if not practice:
        return None
    return PracticeRef.model_validate(practice)


def _question_ref(question: Optional[Question]) -> Optional[QuestionRef]:
    if not question:
        return None
    return QuestionRef.model_validate(question)


def serialize_admin_user(user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        name=user.name,
        surname=user.surname,
        age=user.age,
        email=user.email,
        company_id=user.company_id,
        company=_company_ref(user.company),
        group_name=user.group_name,
    )


def _derive_vacancy_status(vacancy: Created_Vacancy, today: Optional[date] = None) -> str:
    today = today or date.today()
    if vacancy.is_available is False:
        return "Closed"
    if vacancy.start_date and today < vacancy.start_date:
        return "Upcoming"
    if vacancy.end_date and today > vacancy.end_date:
        return "Expired"
    return "Open"


def serialize_admin_vacancy(
    vacancy: Created_Vacancy,
    candidate_count: Optional[int] = None,
    today: Optional[date] = None,
) -> AdminVacancyOut:
    return AdminVacancyOut(
        id=vacancy.id,
        job_name=vacancy.job_name,
        job_description=vacancy.job_description,
        tag=vacancy.tag,
        start_date=vacancy.start_date,
        end_date=vacancy.end_date,
        company_id=vacancy.company_id,
        company=_company_ref(vacancy.company),
        candidate_count=candidate_count if candidate_count is not None else (vacancy.candidate_count or 0),
        is_available=vacancy.is_available,
        status=_derive_vacancy_status(vacancy, today=today),
        practice_id=vacancy.practice_id,
    )


def _candidate_count_map(db: Session, vacancy_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not vacancy_ids:
        return {}
    rows = (
        db.query(Candidate.vacancy_id, func.count(Candidate.id))
        .filter(Candidate.vacancy_id.in_(list(vacancy_ids)))
        .group_by(Candidate.vacancy_id)
        .all()
    )
    return {row[0]: int(row[1]) for row in rows}


def serialize_admin_candidate(candidate: Candidate) -> AdminCandidateOut:
    vacancy = candidate.vacancy
    company = vacancy.company if vacancy else None
    return AdminCandidateOut(
        id=candidate.id,
        user_id=candidate.user_id,
        user=_user_ref(candidate.user),
        vacancy_id=candidate.vacancy_id,
        vacancy=_vacancy_ref(vacancy),
        company=_company_ref(company),
        full_name=candidate.full_name,
        status=candidate.status,
        resume_loc=candidate.resume_loc,
        ai_score=candidate.ai_score,
        created_at=candidate.created_at,
        education=candidate.education,
        experience=candidate.experience,
        skills=candidate.skills,
    )


def _practice_counts_map(
    db: Session,
    practice_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, tuple[int, int]]:
    """Return {practice_id: (assignment_count, completed_count)} in one trip."""
    if not practice_ids:
        return {}
    rows = (
        db.query(
            PracticeAssignment.practice_id,
            func.count(PracticeAssignment.assignment_id).label("assigned"),
            func.count(case((PracticeAssignment.is_completed == True, 1))).label("completed"),
        )
        .filter(PracticeAssignment.practice_id.in_(list(practice_ids)))
        .group_by(PracticeAssignment.practice_id)
        .all()
    )
    return {row.practice_id: (int(row.assigned), int(row.completed)) for row in rows}


def serialize_practice(
    practice: Practice,
    assignment_count: Optional[int] = None,
    completed_count: Optional[int] = None,
) -> PracticeOut:
    return PracticeOut(
        practice_id=practice.practice_id,
        title=practice.title,
        description=practice.description,
        duration_minutes=practice.duration_minutes,
        deadline=practice.deadline,
        question_ids=list(practice.question_ids or []),
        tags=list(practice.tags or []),
        is_valid=practice.is_valid,
        created_at=practice.created_at,
        question_count=len(practice.question_ids or []),
        assignment_count=assignment_count,
        completed_count=completed_count,
    )


def _latest_session_map(
    db: Session,
    practice_id: uuid.UUID,
    user_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, TestSession]:
    """For each user, return their most recent TestSession for this practice."""
    if not user_ids:
        return {}
    rows = (
        db.query(TestSession)
        .filter(
            TestSession.practice_id == practice_id,
            TestSession.user_id.in_(list(user_ids)),
        )
        .order_by(TestSession.user_id, TestSession.started_time.desc())
        .all()
    )
    latest: dict[uuid.UUID, TestSession] = {}
    for row in rows:
        if row.user_id not in latest:
            latest[row.user_id] = row
    return latest


def serialize_practice_assignment(
    assignment: PracticeAssignment,
    latest_session: Optional[TestSession] = None,
) -> PracticeAssignmentOut:
    return PracticeAssignmentOut(
        assignment_id=assignment.assignment_id,
        practice_id=assignment.practice_id,
        practice=_practice_ref(assignment.practice),
        user_id=assignment.user_id,
        user=_user_ref(assignment.user),
        assigned_at=assignment.assigned_at,
        is_completed=assignment.is_completed,
        completed_at=assignment.completed_at,
        latest_session_id=latest_session.session_id if latest_session else None,
        latest_score=float(latest_session.overall_points) if latest_session else None,
        latest_session_finished=latest_session.is_finished if latest_session else None,
    )


def _answer_counts_map(
    db: Session,
    session_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, tuple[int, int]]:
    """Return {session_id: (answered_count, correct_count)} in one trip."""
    if not session_ids:
        return {}
    rows = (
        db.query(
            UserAnswer.session_id,
            func.count(UserAnswer.id).label("answered"),
            func.count(case((UserAnswer.is_correct == True, 1))).label("correct"),
        )
        .filter(UserAnswer.session_id.in_(list(session_ids)))
        .group_by(UserAnswer.session_id)
        .all()
    )
    return {row.session_id: (int(row.answered), int(row.correct)) for row in rows}


def _derive_session_status_label(session: TestSession) -> str:
    score = int(session.overall_points or 0)
    if session.is_finished:
        return f"Passed ({score}%)" if score >= 60 else f"Failed ({score}%)"
    return "In Progress"


def serialize_test_session(
    session: TestSession,
    answered: Optional[int] = None,
    correct: Optional[int] = None,
    total: Optional[int] = None,
) -> AdminTestSessionOut:
    practice = session.practice
    return AdminTestSessionOut(
        session_id=session.session_id,
        practice_id=session.practice_id,
        practice=_practice_ref(practice),
        user_id=session.user_id,
        user=_user_ref(session.user),
        overall_points=float(session.overall_points or 0),
        is_finished=session.is_finished,
        started_time=session.started_time,
        answered_questions=answered,
        correct_answers=correct,
        total_questions=total if total is not None else (
            len(practice.question_ids) if practice and practice.question_ids else None
        ),
        status_label=_derive_session_status_label(session),
    )


def serialize_user_answer(
    answer: UserAnswer,
    question: Optional[Question] = None,
) -> AdminUserAnswerOut:
    question_text: Optional[str] = None
    user_answer_text: Optional[str] = None
    correct_answer_id: Optional[uuid.UUID] = None
    correct_answer_text: Optional[str] = None

    if question:
        question_text = question.text
        correct_answer_id = question.correct_answer
        for option in question.options or []:
            opt_id = str(option.get("id")) if isinstance(option, dict) else None
            opt_text = option.get("text") if isinstance(option, dict) else None
            if not opt_id:
                continue
            if answer.user_answer and str(answer.user_answer) == opt_id:
                user_answer_text = opt_text
            if correct_answer_id and str(correct_answer_id) == opt_id:
                correct_answer_text = opt_text

    return AdminUserAnswerOut(
        id=answer.id,
        session_id=answer.session_id,
        question_id=answer.question_id,
        question=_question_ref(question),
        question_text=question_text,
        user_answer=answer.user_answer,
        user_answer_text=user_answer_text,
        correct_answer_id=correct_answer_id,
        correct_answer_text=correct_answer_text,
        is_correct=answer.is_correct,
        points_awarded=answer.points_awarded,
        time_spent=answer.time_spent,
    )


def _check_user_dependents(db: Session, user_id: uuid.UUID) -> dict[str, int]:
    """Return a dict of dependent record counts for a user."""
    return {
        "test_sessions": db.query(func.count(TestSession.session_id))
        .filter(TestSession.user_id == user_id)
        .scalar() or 0,
        "assignments": db.query(func.count(PracticeAssignment.assignment_id))
        .filter(PracticeAssignment.user_id == user_id)
        .scalar() or 0,
        "candidate_profiles": db.query(func.count(Candidate.id))
        .filter(Candidate.user_id == user_id)
        .scalar() or 0,
    }


@router.get("/dashboard/summary", response_model=AdminDashboardSummary)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    """Returns dashboard summary stats.

    Each metric used to issue its own COUNT/AVG query. We now collapse each
    table into a single aggregate round trip using conditional COUNTs.
    """

    is_superadmin = admin_user.role == Role.SUPERADMIN or not admin_user.company_id
    company_id = admin_user.company_id

    # --- Users ---
    user_q = db.query(func.count(User.id))
    if not is_superadmin:
        user_q = user_q.filter(User.company_id == company_id)
    total_users = user_q.scalar() or 0

    # --- Vacancies (total + active in one trip) ---
    vacancy_q = db.query(
        func.count(Created_Vacancy.id),
        func.count(case((Created_Vacancy.is_available == True, 1))),
    )
    if not is_superadmin:
        vacancy_q = vacancy_q.filter(Created_Vacancy.company_id == company_id)
    total_vacancies, active_vacancies = vacancy_q.one()

    # --- Candidates (joined to vacancy for scoping) ---
    candidate_q = db.query(func.count(Candidate.id)).outerjoin(
        Created_Vacancy, Candidate.vacancy_id == Created_Vacancy.id
    )
    if not is_superadmin:
        candidate_q = candidate_q.filter(Created_Vacancy.company_id == company_id)
    total_candidates = candidate_q.scalar() or 0

    # --- Practices (total + active in one trip) ---
    total_practices, active_practices = db.query(
        func.count(Practice.practice_id),
        func.count(case((Practice.is_valid == True, 1))),
    ).one()

    # --- Questions ---
    total_questions = db.query(func.count(Question.id)).scalar() or 0

    # --- Test sessions (count active/completed + avg in one trip) ---
    session_q = db.query(
        func.count(case((TestSession.is_finished == False, 1))),
        func.count(case((TestSession.is_finished == True, 1))),
        func.avg(case((TestSession.is_finished == True, TestSession.overall_points))),
    ).join(User, TestSession.user_id == User.id)
    if not is_superadmin:
        session_q = session_q.filter(User.company_id == company_id)
    active_sessions, completed_sessions, average_score = session_q.one()

    return {
        "total_users": int(total_users),
        "total_candidates": int(total_candidates),
        "total_vacancies": int(total_vacancies or 0),
        "active_vacancies": int(active_vacancies or 0),
        "total_practices": int(total_practices or 0),
        "active_practices": int(active_practices or 0),
        "total_questions": int(total_questions),
        "active_test_sessions": int(active_sessions or 0),
        "completed_test_sessions": int(completed_sessions or 0),
        "average_test_score": int(average_score or 0),
    }


@router.get("/dashboard/students", response_model=AdminStudentStatsResponse)
def get_student_stats(
    group_name: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    """Returns aggregated stats per student.

    Previous implementation issued ~6 queries per row (N+1 explosion). This
    version pulls the page of users in one query and then collects all
    PracticeAssignment + TestSession aggregates in two grouped queries.
    """
    query = apply_admin_user_scope(db.query(User).filter(User.role == Role.USER), admin_user)

    if group_name:
        query = query.filter(User.group_name == group_name)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(pattern),
                User.name.ilike(pattern),
                User.surname.ilike(pattern),
                User.email.ilike(pattern),
                User.group_name.ilike(pattern),
            )
        )

    total = query.with_entities(func.count(User.id)).scalar() or 0
    users = (
        query.order_by(User.surname.asc(), User.name.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    if not users:
        return {"items": [], "total": int(total), "offset": offset, "limit": limit}

    user_ids = [u.id for u in users]

    # Aggregate practice assignments per user in one trip.
    assignment_rows = (
        db.query(
            PracticeAssignment.user_id,
            func.count(PracticeAssignment.assignment_id).label("assigned"),
            func.count(
                case((PracticeAssignment.is_completed == True, 1))
            ).label("completed"),
        )
        .filter(PracticeAssignment.user_id.in_(user_ids))
        .group_by(PracticeAssignment.user_id)
        .all()
    )
    assignment_map = {row.user_id: row for row in assignment_rows}

    # Aggregate test sessions per user in one trip.
    session_rows = (
        db.query(
            TestSession.user_id,
            func.count(case((TestSession.is_finished == False, 1))).label("active"),
            func.count(case((TestSession.is_finished == True, 1))).label("completed"),
            func.avg(
                case((TestSession.is_finished == True, TestSession.overall_points))
            ).label("avg_score"),
            func.max(TestSession.started_time).label("last_activity"),
        )
        .filter(TestSession.user_id.in_(user_ids))
        .group_by(TestSession.user_id)
        .all()
    )
    session_map = {row.user_id: row for row in session_rows}

    items = []
    for user in users:
        a = assignment_map.get(user.id)
        s = session_map.get(user.id)
        assigned = int(a.assigned) if a else 0
        completed_assignments = int(a.completed) if a else 0
        active_sessions = int(s.active) if s else 0
        completed_sessions = int(s.completed) if s else 0
        avg_score = float(s.avg_score) if s and s.avg_score is not None else 0.0
        last_activity = s.last_activity if s else None

        items.append(
            {
                "id": user.id,
                "username": user.username,
                "name": user.name,
                "surname": user.surname,
                "email": user.email,
                "group_name": user.group_name,
                "assigned_tests": assigned,
                "completed_assignments": completed_assignments,
                "pending_assignments": max(assigned - completed_assignments, 0),
                "active_sessions": active_sessions,
                "completed_sessions": completed_sessions,
                "average_score": int(avg_score),
                "last_activity_at": last_activity,
            }
        )

    return {"items": items, "total": int(total), "offset": offset, "limit": limit}


@router.get("/users", response_model=AdminPagedUsers)
def list_users(
    role: Optional[Role] = None,
    search: Optional[str] = None,
    company_id: Optional[uuid.UUID] = None,
    group_name: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = apply_admin_user_scope(db.query(User), admin_user)

    if role:
        query = query.filter(User.role == role)
    if company_id:
        if admin_user.role != Role.SUPERADMIN and company_id != admin_user.company_id:
            raise HTTPException(status_code=403, detail="Company is outside this admin's scope.")
        query = query.filter(User.company_id == company_id)
    if group_name:
        query = query.filter(User.group_name == group_name)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(pattern),
                User.name.ilike(pattern),
                User.surname.ilike(pattern),
                User.email.ilike(pattern),
                User.group_name.ilike(pattern),
            )
        )

    total = query.count()
    users = (
        query.options(joinedload(User.company))
        .order_by(User.username.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return AdminPagedUsers(
        items=[serialize_admin_user(u) for u in users],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/users/search", response_model=AdminUserSearchResponse)
def search_users(
    q: str = Query("", description="Search username, name, surname, email, or group"),
    role: Optional[Role] = None,
    group_name: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = apply_admin_user_scope(db.query(User), admin_user)

    if role:
        query = query.filter(User.role == role)
    if group_name:
        query = query.filter(User.group_name == group_name)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(
                User.username.ilike(pattern),
                User.name.ilike(pattern),
                User.surname.ilike(pattern),
                User.email.ilike(pattern),
                User.group_name.ilike(pattern),
            )
        )

    total = query.count()
    users = (
        query.options(joinedload(User.company))
        .order_by(User.username.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return AdminUserSearchResponse(
        items=[serialize_admin_user(u) for u in users],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/users", response_model=AdminUserCreatedOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: AdminUserCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    ensure_role_can_be_created(data.role, admin_user)
    company_id = resolve_company_id(data.company_id, admin_user)
    practice = get_practice_or_404(db, data.practice_id) if data.practice_id else None
    username = data.username or generate_unique_username(data.name, data.surname, db)

    if db.query(User.id).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="Username already exists.")

    raw_password = data.password or generate_random_password()
    user = User(
        id=uuid.uuid4(),
        username=username,
        role=data.role,
        password=hash_password(raw_password),
        company_id=company_id,
        name=data.name,
        surname=data.surname,
        age=data.age,
        email=str(data.email) if data.email else None,
        group_name=data.group_name,
        # U2: admin-created accounts must set their own password on first login.
        must_change_password=True,
    )

    db.add(user)
    db.flush()

    if practice:
        create_assignments(db, practice.practice_id, [user.id])

    db.commit()
    db.refresh(user)

    result = serialize_created_user(user, raw_password, data.practice_id)
    if data.send_invitation:
        try:
            if practice:
                send_practice_invitation(
                    user,
                    practice,
                    raw_password=raw_password,
                    frontend_test_base_url=data.frontend_test_base_url,
                )
            else:
                if not user.email:
                    raise EmailDeliveryError(f"{user.username} has no email address.")
                send_email(
                    to_email=user.email,
                    subject="Your TalentFlow account",
                    plain_text=(
                        f"Hello {user.name},\n\n"
                        f"Your account has been created.\n"
                        f"Username: {user.username}\n"
                        f"Password: {raw_password}"
                    ),
                )
            result.invitation_sent = True
        except EmailDeliveryError as exc:
            result.invitation_error = str(exc)

    return result


@router.post("/users/bulk", response_model=AdminBulkUserCreateResponse)
def bulk_create_users(
    data: AdminBulkUserCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    ensure_role_can_be_created(data.role, admin_user)
    company_id = resolve_company_id(data.company_id, admin_user)
    practice = get_practice_or_404(db, data.practice_id) if data.practice_id else None
    reserved_usernames = set()
    created_results: list[AdminUserCreatedOut] = []
    existing_results: list[AdminUserCreatedOut] = []
    failed: list[dict] = []
    email_jobs = []

    # Pre-fetch existing users by email (the import identity key) in one query
    # instead of a SELECT per row.
    requested_emails = {str(item.email) for item in data.users if item.email}

    email_map: dict[str, User] = {}
    if requested_emails:
        rows = (
            db.query(User)
            .filter(User.email.in_(requested_emails))
            .all()
        )
        email_map = {u.email: u for u in rows}

    for item in data.users:
        # "Same person" is keyed on email (the stable identity for imports).
        # A username collision with a *different* person is auto-renamed below
        # rather than treated as the same user.
        existing = email_map.get(str(item.email)) if item.email else None

        if existing:
            if not data.skip_existing:
                failed.append({"email": str(item.email), "reason": "User already exists."})
                continue
            try:
                ensure_user_visible_to_admin(existing, admin_user)
            except HTTPException:
                failed.append({"email": str(item.email), "reason": "Existing user is outside admin scope."})
                continue

            if practice:
                create_assignments(db, practice.practice_id, [existing.id])
            result = serialize_created_user(existing, None, data.practice_id, already_existed=True)
            existing_results.append(result)
            if data.send_invitation and practice:
                email_jobs.append((existing, practice, None, result))
            continue

        # Cross-cutting: an explicitly-supplied duplicate username is
        # auto-renamed (john.doe -> john.doe1) instead of failing the row.
        if item.username:
            username = dedupe_username(item.username, db, reserved=reserved_usernames)
        else:
            username = generate_unique_username(
                item.name,
                item.surname,
                db,
                reserved=reserved_usernames,
            )
        raw_password = generate_random_password()
        user = User(
            id=uuid.uuid4(),
            username=username,
            role=data.role,
            password=hash_password(raw_password),
            company_id=company_id,
            name=item.name,
            surname=item.surname,
            age=item.age,
            email=str(item.email),
            group_name=item.group_name or data.group_name,
            # U2: bulk-imported accounts must set their own password on first login.
            must_change_password=True,
        )
        db.add(user)
        db.flush()

        if practice:
            create_assignments(db, practice.practice_id, [user.id])

        result = serialize_created_user(user, raw_password, data.practice_id)
        created_results.append(result)
        if data.send_invitation:
            email_jobs.append((user, practice, raw_password, result))

    db.commit()

    for user, practice, raw_password, result in email_jobs:
        try:
            if practice:
                send_practice_invitation(
                    user,
                    practice,
                    raw_password=raw_password,
                    frontend_test_base_url=data.frontend_test_base_url,
                )
            else:
                if not user.email:
                    raise EmailDeliveryError(f"{user.username} has no email address.")
                send_email(
                    to_email=user.email,
                    subject="Your TalentFlow account",
                    plain_text=(
                        f"Hello {user.name},\n\n"
                        f"Your account has been created.\n"
                        f"Username: {user.username}\n"
                        f"Password: {raw_password}"
                    ),
                )
            result.invitation_sent = True
        except EmailDeliveryError as exc:
            result.invitation_error = str(exc)

    return {
        "created": created_results,
        "existing": existing_results,
        "failed": failed,
        "created_count": len(created_results),
        "existing_count": len(existing_results),
        "failed_count": len(failed),
    }


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    user = (
        apply_admin_user_scope(db.query(User), admin_user)
        .options(joinedload(User.company))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    assignment_row = (
        db.query(
            func.count(PracticeAssignment.assignment_id).label("assigned"),
            func.count(case((PracticeAssignment.is_completed == True, 1))).label("completed"),
        )
        .filter(PracticeAssignment.user_id == user_id)
        .one()
    )
    session_row = (
        db.query(
            func.count(TestSession.session_id).label("total"),
            func.count(case((TestSession.is_finished == True, 1))).label("finished"),
            func.count(case((TestSession.is_finished == False, 1))).label("active"),
            func.coalesce(func.avg(case((TestSession.is_finished == True, TestSession.overall_points))), 0).label("avg_score"),
            func.max(TestSession.started_time).label("last_activity"),
        )
        .filter(TestSession.user_id == user_id)
        .one()
    )

    base = serialize_admin_user(user)
    return AdminUserDetail(
        **base.model_dump(),
        assigned_practices=int(assignment_row.assigned or 0),
        completed_practices=int(assignment_row.completed or 0),
        active_sessions=int(session_row.active or 0),
        completed_sessions=int(session_row.finished or 0),
        average_score=int(session_row.avg_score or 0),
        last_activity_at=session_row.last_activity,
    )


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: uuid.UUID,
    data: AdminUserUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    user = apply_admin_user_scope(db.query(User), admin_user).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = data.model_dump(exclude_unset=True)

    if "role" in update_data and update_data["role"] is not None:
        ensure_role_can_be_created(update_data["role"], admin_user)
    if "company_id" in update_data:
        if update_data["company_id"] is None and admin_user.role != Role.SUPERADMIN:
            raise HTTPException(status_code=403, detail="Only SUPERADMIN can clear company assignment.")
        update_data["company_id"] = resolve_company_id(update_data.get("company_id"), admin_user)
    if "email" in update_data and update_data["email"] is not None:
        update_data["email"] = str(update_data["email"])

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    db.refresh(user, ["company"])
    return serialize_admin_user(user)


@router.delete("/users/{user_id}", response_model=AdminDeleteResult)
def delete_user(
    user_id: uuid.UUID,
    force: bool = Query(False, description="Delete the user even if dependent records exist."),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    if user_id == admin_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")

    user = apply_admin_user_scope(db.query(User), admin_user).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == Role.SUPERADMIN and admin_user.role != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Only SUPERADMIN can delete a SUPERADMIN account.")

    dependents = _check_user_dependents(db, user_id)
    total_dependents = sum(dependents.values())
    if total_dependents and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "User has dependent records. Pass force=true to delete anyway.",
                "dependents": dependents,
            },
        )

    if total_dependents:
        db.query(UserAnswer).filter(
            UserAnswer.session_id.in_(
                db.query(TestSession.session_id).filter(TestSession.user_id == user_id)
            )
        ).delete(synchronize_session=False)
        db.query(TestSession).filter(TestSession.user_id == user_id).delete(synchronize_session=False)
        db.query(PracticeAssignment).filter(PracticeAssignment.user_id == user_id).delete(synchronize_session=False)
        db.query(Candidate).filter(Candidate.user_id == user_id).delete(synchronize_session=False)

    db.delete(user)
    db.commit()

    message = "User deleted."
    if total_dependents:
        message = (
            f"User deleted along with {total_dependents} dependent record(s) "
            f"({dependents})."
        )
    return AdminDeleteResult(id=user_id, deleted=True, message=message)


@router.post(
    "/users/{user_id}/password-reset",
    response_model=AdminUserPasswordResetResult,
)
def reset_user_password(
    user_id: uuid.UUID,
    data: AdminUserPasswordReset,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    user = apply_admin_user_scope(db.query(User), admin_user).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == Role.SUPERADMIN and admin_user.role != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Only SUPERADMIN can reset a SUPERADMIN password.")

    new_password = data.new_password or generate_random_password()
    user.password = hash_password(new_password)
    # U2: an admin reset forces the user to choose a new password on next login.
    user.must_change_password = True
    db.commit()

    result = AdminUserPasswordResetResult(
        id=user.id,
        username=user.username,
        password=new_password,
        notification_sent=False,
    )

    if data.notify_user:
        if not user.email:
            result.notification_error = "User has no email address on file."
        else:
            try:
                send_email(
                    to_email=user.email,
                    subject="Your TalentFlow password has been reset",
                    plain_text=(
                        f"Hello {user.name},\n\n"
                        f"An administrator has reset your password.\n"
                        f"New password: {new_password}\n\n"
                        f"Please log in and change it as soon as possible."
                    ),
                )
                result.notification_sent = True
            except EmailDeliveryError as exc:
                result.notification_error = str(exc)

    return result


@router.get("/companies", response_model=AdminPagedCompanies)
def list_companies(
    search: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = db.query(Company)

    if admin_user.role != Role.SUPERADMIN and admin_user.company_id:
        query = query.filter(Company.id == admin_user.company_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(Company.name.ilike(pattern), Company.email.ilike(pattern), Company.INN.ilike(pattern))
        )

    total = query.count()
    companies = query.order_by(Company.name.asc()).offset(offset).limit(limit).all()
    return AdminPagedCompanies(
        items=[CompanyOut.model_validate(c) for c in companies],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    data: CompanyCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    if admin_user.role != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Only SUPERADMIN can create companies.")

    existing = db.query(Company.id).filter(Company.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Company name already exists.")

    company = Company(
        id=uuid.uuid4(),
        name=data.name,
        phone_number=data.phone_number,
        INN=data.INN,
        email=str(data.email) if data.email else None,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return CompanyOut.model_validate(company)


@router.get("/companies/{company_id}", response_model=CompanyDetail)
def get_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    if admin_user.role != Role.SUPERADMIN and admin_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Company is outside this admin's scope.")

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    user_count = db.query(func.count(User.id)).filter(User.company_id == company_id).scalar() or 0
    vacancy_count = (
        db.query(func.count(Created_Vacancy.id))
        .filter(Created_Vacancy.company_id == company_id)
        .scalar()
        or 0
    )
    candidate_count = (
        db.query(func.count(Candidate.id))
        .join(Created_Vacancy, Candidate.vacancy_id == Created_Vacancy.id)
        .filter(Created_Vacancy.company_id == company_id)
        .scalar()
        or 0
    )

    base = CompanyOut.model_validate(company)
    return CompanyDetail(
        **base.model_dump(),
        user_count=int(user_count),
        vacancy_count=int(vacancy_count),
        candidate_count=int(candidate_count),
    )


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: uuid.UUID,
    data: CompanyUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    if admin_user.role != Role.SUPERADMIN and admin_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Company is outside this admin's scope.")

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    update_data = data.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != company.name:
        clash = (
            db.query(Company.id)
            .filter(Company.name == update_data["name"], Company.id != company_id)
            .first()
        )
        if clash:
            raise HTTPException(status_code=409, detail="Another company already uses that name.")
    if "email" in update_data and update_data["email"] is not None:
        update_data["email"] = str(update_data["email"])

    for field, value in update_data.items():
        setattr(company, field, value)

    db.commit()
    db.refresh(company)
    return CompanyOut.model_validate(company)


@router.delete("/companies/{company_id}", response_model=AdminDeleteResult)
def delete_company(
    company_id: uuid.UUID,
    force: bool = Query(False, description="Delete the company even if it still has users or vacancies."),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    if admin_user.role != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Only SUPERADMIN can delete companies.")

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    user_count = db.query(func.count(User.id)).filter(User.company_id == company_id).scalar() or 0
    vacancy_count = (
        db.query(func.count(Created_Vacancy.id))
        .filter(Created_Vacancy.company_id == company_id)
        .scalar()
        or 0
    )

    dependents = {"users": int(user_count), "vacancies": int(vacancy_count)}
    if (user_count or vacancy_count) and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Company still has users or vacancies. Pass force=true to detach and delete.",
                "dependents": dependents,
            },
        )

    if user_count:
        db.query(User).filter(User.company_id == company_id).update(
            {User.company_id: None}, synchronize_session=False
        )
    if vacancy_count:
        vacancy_ids = [
            row[0]
            for row in db.query(Created_Vacancy.id).filter(Created_Vacancy.company_id == company_id).all()
        ]
        if vacancy_ids:
            db.query(Candidate).filter(Candidate.vacancy_id.in_(vacancy_ids)).delete(
                synchronize_session=False
            )
            db.query(Created_Vacancy).filter(Created_Vacancy.id.in_(vacancy_ids)).delete(
                synchronize_session=False
            )

    db.delete(company)
    db.commit()

    message = "Company deleted."
    if user_count or vacancy_count:
        message = (
            f"Company deleted. Detached {user_count} user(s) and removed {vacancy_count} vacancy/vacancies."
        )
    return AdminDeleteResult(id=company_id, deleted=True, message=message)


@router.get("/companies/{company_id}/users", response_model=AdminPagedUsers)
def list_company_users(
    company_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    if admin_user.role != Role.SUPERADMIN and admin_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Company is outside this admin's scope.")

    query = db.query(User).filter(User.company_id == company_id)
    total = query.count()
    users = (
        query.options(joinedload(User.company))
        .order_by(User.username.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return AdminPagedUsers(
        items=[serialize_admin_user(u) for u in users],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/companies/{company_id}/vacancies", response_model=AdminPagedVacancies)
def list_company_vacancies(
    company_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    if admin_user.role != Role.SUPERADMIN and admin_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Company is outside this admin's scope.")

    query = db.query(Created_Vacancy).filter(Created_Vacancy.company_id == company_id)
    total = query.count()
    vacancies = (
        query.options(joinedload(Created_Vacancy.company))
        .order_by(Created_Vacancy.start_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    counts = _candidate_count_map(db, [v.id for v in vacancies])
    today = date.today()
    return AdminPagedVacancies(
        items=[
            serialize_admin_vacancy(v, candidate_count=counts.get(v.id, 0), today=today)
            for v in vacancies
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/vacancies", response_model=AdminPagedVacancies)
def list_vacancies(
    company_id: Optional[uuid.UUID] = None,
    is_available: Optional[bool] = None,
    status_filter: Optional[str] = Query(None, alias="status", description="Open / Upcoming / Expired / Closed"),
    search: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = apply_admin_vacancy_scope(db.query(Created_Vacancy), admin_user)

    if company_id:
        if admin_user.role != Role.SUPERADMIN and company_id != admin_user.company_id:
            raise HTTPException(status_code=403, detail="Company is outside this admin's scope.")
        query = query.filter(Created_Vacancy.company_id == company_id)
    if is_available is not None:
        query = query.filter(Created_Vacancy.is_available == is_available)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(Created_Vacancy.job_name.ilike(pattern), Created_Vacancy.tag.ilike(pattern))
        )

    total = query.count()
    vacancies = (
        query.options(joinedload(Created_Vacancy.company))
        .order_by(Created_Vacancy.start_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    today = date.today()
    if status_filter:
        vacancies = [v for v in vacancies if _derive_vacancy_status(v, today=today) == status_filter]

    counts = _candidate_count_map(db, [v.id for v in vacancies])
    return AdminPagedVacancies(
        items=[
            serialize_admin_vacancy(v, candidate_count=counts.get(v.id, 0), today=today)
            for v in vacancies
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/vacancies", response_model=AdminVacancyOut, status_code=status.HTTP_201_CREATED)
def create_vacancy(
    data: AdminVacancyCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    company_id = resolve_company_id(data.company_id, admin_user)
    if not company_id:
        raise HTTPException(status_code=400, detail="company_id is required for this admin.")

    if data.end_date < data.start_date:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date.")

    if data.practice_id is not None:
        get_practice_or_404(db, data.practice_id)

    vacancy = Created_Vacancy(
        id=uuid.uuid4(),
        job_name=data.job_name,
        job_description=data.job_description,
        tag=data.tag,
        start_date=data.start_date,
        end_date=data.end_date,
        company_id=company_id,
        is_available=data.is_available,
        practice_id=data.practice_id,
    )
    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)
    db.refresh(vacancy, ["company"])
    return serialize_admin_vacancy(vacancy, candidate_count=0)


@router.get("/vacancies/{vacancy_id}", response_model=AdminVacancyDetail)
def get_vacancy(
    vacancy_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    vacancy = (
        apply_admin_vacancy_scope(db.query(Created_Vacancy), admin_user)
        .options(joinedload(Created_Vacancy.company))
        .filter(Created_Vacancy.id == vacancy_id)
        .first()
    )
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    rows = (
        db.query(Candidate.status, func.count(Candidate.id))
        .filter(Candidate.vacancy_id == vacancy_id)
        .group_by(Candidate.status)
        .all()
    )
    breakdown = {status_value: int(count) for status_value, count in rows}
    total_candidates = sum(breakdown.values())

    base = serialize_admin_vacancy(vacancy, candidate_count=total_candidates)
    return AdminVacancyDetail(
        **base.model_dump(),
        candidate_status_breakdown=breakdown,
    )


@router.patch("/vacancies/{vacancy_id}", response_model=AdminVacancyOut)
def update_vacancy(
    vacancy_id: uuid.UUID,
    data: AdminVacancyUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    vacancy = apply_admin_vacancy_scope(db.query(Created_Vacancy), admin_user).filter(
        Created_Vacancy.id == vacancy_id
    ).first()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    if "company_id" in update_data:
        update_data["company_id"] = resolve_company_id(update_data["company_id"], admin_user)
    if update_data.get("practice_id") is not None:
        get_practice_or_404(db, update_data["practice_id"])

    start_date = update_data.get("start_date", vacancy.start_date)
    end_date = update_data.get("end_date", vacancy.end_date)
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date.")

    for field, value in update_data.items():
        setattr(vacancy, field, value)

    db.commit()
    db.refresh(vacancy)
    db.refresh(vacancy, ["company"])

    candidate_count = (
        db.query(func.count(Candidate.id)).filter(Candidate.vacancy_id == vacancy_id).scalar() or 0
    )
    return serialize_admin_vacancy(vacancy, candidate_count=int(candidate_count))


@router.delete("/vacancies/{vacancy_id}", response_model=AdminDeleteResult)
def delete_vacancy(
    vacancy_id: uuid.UUID,
    force: bool = Query(False, description="Delete the vacancy along with its candidates."),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    vacancy = apply_admin_vacancy_scope(db.query(Created_Vacancy), admin_user).filter(
        Created_Vacancy.id == vacancy_id
    ).first()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    candidate_count = (
        db.query(func.count(Candidate.id)).filter(Candidate.vacancy_id == vacancy_id).scalar() or 0
    )
    if candidate_count and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Vacancy still has candidates. Pass force=true to delete them too.",
                "dependents": {"candidates": int(candidate_count)},
            },
        )

    if candidate_count:
        db.query(Candidate).filter(Candidate.vacancy_id == vacancy_id).delete(synchronize_session=False)
    db.delete(vacancy)
    db.commit()

    message = "Vacancy deleted."
    if candidate_count:
        message = f"Vacancy deleted along with {int(candidate_count)} candidate(s)."
    return AdminDeleteResult(id=vacancy_id, deleted=True, message=message)


@router.get("/vacancies/{vacancy_id}/candidates", response_model=AdminPagedCandidates)
def list_vacancy_candidates(
    vacancy_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    vacancy = apply_admin_vacancy_scope(db.query(Created_Vacancy), admin_user).filter(
        Created_Vacancy.id == vacancy_id
    ).first()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    query = db.query(Candidate).filter(Candidate.vacancy_id == vacancy_id)
    if status_filter:
        query = query.filter(Candidate.status == status_filter)

    total = query.count()
    candidates = (
        query.options(
            joinedload(Candidate.user),
            joinedload(Candidate.vacancy).joinedload(Created_Vacancy.company),
        )
        .order_by(Candidate.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return AdminPagedCandidates(
        items=[serialize_admin_candidate(c) for c in candidates],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/candidates", response_model=AdminPagedCandidates)
def list_candidates(
    status_filter: Optional[str] = Query(None, alias="status"),
    vacancy_id: Optional[uuid.UUID] = None,
    company_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = db.query(Candidate).join(Created_Vacancy, Candidate.vacancy_id == Created_Vacancy.id)
    query = apply_admin_vacancy_scope(query, admin_user)

    if status_filter:
        query = query.filter(Candidate.status == status_filter)
    if vacancy_id:
        query = query.filter(Candidate.vacancy_id == vacancy_id)
    if company_id:
        if admin_user.role != Role.SUPERADMIN and company_id != admin_user.company_id:
            raise HTTPException(status_code=403, detail="Company is outside this admin's scope.")
        query = query.filter(Created_Vacancy.company_id == company_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Candidate.full_name.ilike(pattern), Candidate.skills.ilike(pattern)))

    total = query.count()
    candidates = (
        query.options(
            joinedload(Candidate.user),
            joinedload(Candidate.vacancy).joinedload(Created_Vacancy.company),
        )
        .order_by(Candidate.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return AdminPagedCandidates(
        items=[serialize_admin_candidate(c) for c in candidates],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/candidates", response_model=AdminCandidateOut, status_code=status.HTTP_201_CREATED)
def create_candidate(
    data: AdminCandidateCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    vacancy = apply_admin_vacancy_scope(db.query(Created_Vacancy), admin_user).filter(
        Created_Vacancy.id == data.vacancy_id
    ).first()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found or outside admin scope.")

    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    existing = (
        db.query(Candidate.id)
        .filter(Candidate.user_id == data.user_id, Candidate.vacancy_id == data.vacancy_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Candidate already exists for this user/vacancy.")

    full_name = data.full_name or f"{user.name} {user.surname}".strip()
    candidate = Candidate(
        id=uuid.uuid4(),
        user_id=data.user_id,
        vacancy_id=data.vacancy_id,
        full_name=full_name,
        status=data.status,
        resume_loc=data.resume_loc,
        ai_score=data.ai_score,
        education=data.education,
        experience=data.experience,
        skills=data.skills,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    db.refresh(candidate, ["user", "vacancy"])
    if candidate.vacancy is not None:
        db.refresh(candidate.vacancy, ["company"])
    return serialize_admin_candidate(candidate)


@router.get("/candidates/{candidate_id}", response_model=AdminCandidateOut)
def get_candidate(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = (
        db.query(Candidate)
        .join(Created_Vacancy, Candidate.vacancy_id == Created_Vacancy.id)
        .options(
            joinedload(Candidate.user),
            joinedload(Candidate.vacancy).joinedload(Created_Vacancy.company),
        )
    )
    query = apply_admin_vacancy_scope(query, admin_user)
    candidate = query.filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return serialize_admin_candidate(candidate)


@router.patch("/candidates/{candidate_id}", response_model=AdminCandidateOut)
def update_candidate(
    candidate_id: uuid.UUID,
    data: AdminCandidateUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = db.query(Candidate).join(Created_Vacancy, Candidate.vacancy_id == Created_Vacancy.id)
    query = apply_admin_vacancy_scope(query, admin_user)
    candidate = query.filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(candidate, field, value)

    db.commit()
    db.refresh(candidate)
    db.refresh(candidate, ["user", "vacancy"])
    if candidate.vacancy is not None:
        db.refresh(candidate.vacancy, ["company"])
    return serialize_admin_candidate(candidate)


@router.patch("/candidates/{candidate_id}/status", response_model=AdminCandidateOut)
def update_candidate_status(
    candidate_id: uuid.UUID,
    update_data: CandidateStatusUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = db.query(Candidate).join(Created_Vacancy, Candidate.vacancy_id == Created_Vacancy.id)
    query = apply_admin_vacancy_scope(query, admin_user)
    candidate = query.filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    previous_status = candidate.status
    candidate.status = update_data.status

    # A3 + U5: fan out to email + in-app notification, but only when the
    # status actually changed. Email failures never block the update.
    notify_result = None
    if previous_status != update_data.status:
        db.refresh(candidate, ["user", "vacancy"])
        vacancy_name = candidate.vacancy.job_name if candidate.vacancy else None
        notify_result = notify_candidate_status_change(
            db,
            candidate,
            update_data.status,
            user=candidate.user,
            vacancy_name=vacancy_name,
        )

    db.commit()
    db.refresh(candidate)
    db.refresh(candidate, ["user", "vacancy"])
    if candidate.vacancy is not None:
        db.refresh(candidate.vacancy, ["company"])

    payload = serialize_admin_candidate(candidate)
    if notify_result is not None:
        payload.email_sent = notify_result.email_sent
        payload.email_error = notify_result.email_error
    return payload


@router.delete("/candidates/{candidate_id}", response_model=AdminDeleteResult)
def delete_candidate(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = db.query(Candidate).join(Created_Vacancy, Candidate.vacancy_id == Created_Vacancy.id)
    query = apply_admin_vacancy_scope(query, admin_user)
    candidate = query.filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    db.delete(candidate)
    db.commit()
    return AdminDeleteResult(id=candidate_id, deleted=True, message="Candidate deleted.")


@router.get("/questions", response_model=AdminPagedQuestions)
def list_questions(
    category: Optional[str] = None,
    difficulty_min: Optional[float] = Query(None, ge=0),
    difficulty_max: Optional[float] = Query(None, ge=0),
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = db.query(Question)

    if category:
        query = query.filter(Question.category == category)
    if difficulty_min is not None:
        query = query.filter(Question.difficulty_level >= difficulty_min)
    if difficulty_max is not None:
        query = query.filter(Question.difficulty_level <= difficulty_max)
    if search:
        query = query.filter(Question.text.ilike(f"%{search}%"))

    total = query.count()
    questions = (
        query.order_by(Question.category.asc(), Question.difficulty_level.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return AdminPagedQuestions(
        items=[QuestionOut.model_validate(q) for q in questions],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/questions", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def create_question(
    data: QuestionCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    options, option_ids = normalize_question_options(data.options)
    correct_answer = resolve_correct_answer(option_ids, data.correct_answer, data.correct_option_index)

    question = Question(
        id=uuid.uuid4(),
        text=data.text.strip(),
        options=options,
        correct_answer=correct_answer,
        difficulty_level=data.difficulty_level,
        category=data.category,
        points=data.points,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.post("/questions/bulk", response_model=List[QuestionOut])
def create_questions_bulk(
    questions: List[QuestionCreate],
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    created_questions = []
    for data in questions:
        options, option_ids = normalize_question_options(data.options)
        correct_answer = resolve_correct_answer(option_ids, data.correct_answer, data.correct_option_index)
        question = Question(
            id=uuid.uuid4(),
            text=data.text.strip(),
            options=options,
            correct_answer=correct_answer,
            difficulty_level=data.difficulty_level,
            category=data.category,
            points=data.points,
        )
        db.add(question)
        created_questions.append(question)

    db.commit()
    for question in created_questions:
        db.refresh(question)
    return created_questions


@router.get("/questions/{question_id}", response_model=QuestionOut)
def get_question(
    question_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.patch("/questions/{question_id}", response_model=QuestionOut)
def update_question(
    question_id: uuid.UUID,
    data: QuestionUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    update_data = data.model_dump(exclude_unset=True)

    if "text" in update_data and data.text is not None:
        question.text = data.text.strip()
    if "difficulty_level" in update_data and data.difficulty_level is not None:
        question.difficulty_level = data.difficulty_level
    if "category" in update_data:
        question.category = data.category
    if "points" in update_data and data.points is not None:
        question.points = data.points

    option_ids = [uuid.UUID(str(option["id"])) for option in question.options]
    if data.options is not None:
        normalized_options, option_ids = normalize_question_options(data.options)
        question.options = normalized_options

    if (
        data.options is not None
        or data.correct_answer is not None
        or data.correct_option_index is not None
    ):
        question.correct_answer = resolve_correct_answer(
            option_ids,
            data.correct_answer,
            data.correct_option_index,
            existing_correct_answer=question.correct_answer,
        )

    db.commit()
    db.refresh(question)
    return question


@router.patch("/questions/{question_id}/difficulty", response_model=AdminQuestionDifficultyResult)
def update_question_difficulty(
    question_id: uuid.UUID,
    update_data: DifficultyUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    old_difficulty = question.difficulty_level
    question.difficulty_level = update_data.new_difficulty
    db.add(
        QuestionHistory(
            id=uuid.uuid4(),
            question_id=question.id,
            old_difficulty=old_difficulty,
            new_difficulty=update_data.new_difficulty,
            change_reason=update_data.change_reason,
            changed_by=admin_user.id,
        )
    )
    db.commit()
    db.refresh(question)

    return AdminQuestionDifficultyResult(
        id=question.id,
        text=question.text,
        category=question.category,
        old_difficulty=old_difficulty,
        new_difficulty=question.difficulty_level,
        change_reason=update_data.change_reason,
    )


@router.delete("/questions/{question_id}", response_model=AdminDeleteResult)
def delete_question(
    question_id: uuid.UUID,
    force: bool = Query(False, description="Detach the question from any practices that reference it."),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Detach from practices that still reference this question_id in their
    # question_ids array.
    practices_using = db.query(Practice).filter(Practice.question_ids.contains([question_id])).all()
    if practices_using and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Question is referenced by practices. Pass force=true to detach and delete.",
                "dependents": {"practices": len(practices_using)},
            },
        )

    for practice in practices_using:
        practice.question_ids = [qid for qid in (practice.question_ids or []) if qid != question_id]

    db.query(UserAnswer).filter(UserAnswer.question_id == question_id).delete(synchronize_session=False)
    db.query(QuestionHistory).filter(QuestionHistory.question_id == question_id).delete(
        synchronize_session=False
    )
    db.delete(question)
    db.commit()

    message = "Question deleted."
    if practices_using:
        message = (
            f"Question deleted and detached from {len(practices_using)} practice(s)."
        )
    return AdminDeleteResult(id=question_id, deleted=True, message=message)


@router.get("/questions/{question_id}/history", response_model=AdminPagedQuestionHistory)
def list_question_history(
    question_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = db.query(QuestionHistory).filter(QuestionHistory.question_id == question_id)
    total = query.count()
    rows = (
        query.order_by(QuestionHistory.changed_at.desc()).offset(offset).limit(limit).all()
    )
    return AdminPagedQuestionHistory(
        items=[QuestionHistoryOut.model_validate(r) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/practices", response_model=AdminPagedPractices)
def list_practices(
    is_valid: Optional[bool] = None,
    search: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = db.query(Practice)

    if is_valid is not None:
        query = query.filter(Practice.is_valid == is_valid)
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Practice.title.ilike(pattern), Practice.description.ilike(pattern)))

    total = query.count()
    practices = (
        query.order_by(Practice.created_at.desc()).offset(offset).limit(limit).all()
    )
    counts = _practice_counts_map(db, [p.practice_id for p in practices])
    return AdminPagedPractices(
        items=[
            serialize_practice(
                p,
                assignment_count=counts.get(p.practice_id, (0, 0))[0],
                completed_count=counts.get(p.practice_id, (0, 0))[1],
            )
            for p in practices
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/practices", response_model=PracticeOut, status_code=status.HTTP_201_CREATED)
def create_practice(
    practice_data: PracticeCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    validate_question_ids(db, practice_data.question_ids)

    new_practice = Practice(
        practice_id=uuid.uuid4(),
        title=practice_data.title,
        description=practice_data.description or "",
        duration_minutes=practice_data.duration_minutes,
        question_ids=practice_data.question_ids,
        tags=practice_data.tags,
        is_valid=True,
        deadline=practice_data.deadline,
        created_at=datetime.utcnow(),
    )

    db.add(new_practice)
    db.commit()
    db.refresh(new_practice)
    return serialize_practice(new_practice, assignment_count=0, completed_count=0)


@router.get("/practices/{practice_id}", response_model=PracticeDetail)
def get_practice(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    practice = get_practice_or_404(db, practice_id)

    counts = _practice_counts_map(db, [practice.practice_id])
    assignment_count, completed_count = counts.get(practice.practice_id, (0, 0))

    session_row = (
        db.query(
            func.count(case((TestSession.is_finished == False, 1))).label("active"),
            func.count(case((TestSession.is_finished == True, 1))).label("finished"),
            func.coalesce(
                func.avg(case((TestSession.is_finished == True, TestSession.overall_points))),
                0,
            ).label("avg_score"),
        )
        .filter(TestSession.practice_id == practice.practice_id)
        .one()
    )

    questions: list[QuestionRef] = []
    if practice.question_ids:
        rows = db.query(Question).filter(Question.id.in_(practice.question_ids)).all()
        by_id = {q.id: q for q in rows}
        questions = [QuestionRef.model_validate(by_id[qid]) for qid in practice.question_ids if qid in by_id]

    base = serialize_practice(practice, assignment_count=assignment_count, completed_count=completed_count)
    return PracticeDetail(
        **base.model_dump(),
        questions=questions,
        active_sessions=int(session_row.active or 0),
        finished_sessions=int(session_row.finished or 0),
        average_score=float(session_row.avg_score or 0.0),
    )


@router.get("/practices/{practice_id}/questions", response_model=List[QuestionOut])
def list_practice_questions(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    practice = get_practice_or_404(db, practice_id)
    if not practice.question_ids:
        return []

    questions = db.query(Question).filter(Question.id.in_(practice.question_ids)).all()
    question_by_id = {question.id: question for question in questions}
    return [question_by_id[q_id] for q_id in practice.question_ids if q_id in question_by_id]


@router.patch("/practices/{practice_id}", response_model=PracticeOut)
def update_practice(
    practice_id: uuid.UUID,
    update_data: PracticeUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    practice = get_practice_or_404(db, practice_id)
    data = update_data.model_dump(exclude_unset=True, exclude_none=True)

    if "question_ids" in data:
        validate_question_ids(db, data["question_ids"])

    for field, value in data.items():
        setattr(practice, field, value)

    db.commit()
    db.refresh(practice)
    counts = _practice_counts_map(db, [practice.practice_id])
    assignment_count, completed_count = counts.get(practice.practice_id, (0, 0))
    return serialize_practice(
        practice,
        assignment_count=assignment_count,
        completed_count=completed_count,
    )


@router.delete("/practices/{practice_id}", response_model=AdminDeleteResult)
def delete_practice(
    practice_id: uuid.UUID,
    force: bool = Query(False, description="Delete the practice even if it has assignments or sessions."),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    practice = get_practice_or_404(db, practice_id)

    assignment_count = (
        db.query(func.count(PracticeAssignment.assignment_id))
        .filter(PracticeAssignment.practice_id == practice_id)
        .scalar()
        or 0
    )
    session_count = (
        db.query(func.count(TestSession.session_id))
        .filter(TestSession.practice_id == practice_id)
        .scalar()
        or 0
    )

    dependents = {
        "assignments": int(assignment_count),
        "test_sessions": int(session_count),
    }
    if (assignment_count or session_count) and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Practice still has assignments or sessions. Pass force=true to cascade delete.",
                "dependents": dependents,
            },
        )

    if session_count:
        db.query(UserAnswer).filter(
            UserAnswer.session_id.in_(
                db.query(TestSession.session_id).filter(TestSession.practice_id == practice_id)
            )
        ).delete(synchronize_session=False)
        db.query(TestSession).filter(TestSession.practice_id == practice_id).delete(
            synchronize_session=False
        )
    if assignment_count:
        db.query(PracticeAssignment).filter(
            PracticeAssignment.practice_id == practice_id
        ).delete(synchronize_session=False)

    db.delete(practice)
    db.commit()

    message = "Practice deleted."
    if assignment_count or session_count:
        message = (
            f"Practice deleted along with {assignment_count} assignment(s) and {session_count} session(s)."
        )
    return AdminDeleteResult(id=practice_id, deleted=True, message=message)


@router.get("/practices/{practice_id}/assignments", response_model=AdminPagedAssignments)
def list_practice_assignments(
    practice_id: uuid.UUID,
    is_completed: Optional[bool] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    get_practice_or_404(db, practice_id)
    query = (
        db.query(PracticeAssignment)
        .join(User, PracticeAssignment.user_id == User.id)
    )
    query = query.filter(PracticeAssignment.practice_id == practice_id)
    query = apply_admin_user_scope(query, admin_user)

    if is_completed is not None:
        query = query.filter(PracticeAssignment.is_completed == is_completed)

    total = query.count()
    assignments = (
        query.options(
            joinedload(PracticeAssignment.user),
            joinedload(PracticeAssignment.practice),
        )
        .order_by(PracticeAssignment.assigned_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    latest_map = _latest_session_map(
        db,
        practice_id,
        [a.user_id for a in assignments],
    )
    return AdminPagedAssignments(
        items=[
            serialize_practice_assignment(a, latest_session=latest_map.get(a.user_id))
            for a in assignments
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.patch("/practices/{practice_id}/assignments", response_model=PracticeAssignmentResult)
def manage_advanced_assignments(
    practice_id: uuid.UUID,
    update_data: AdvancedAssignmentUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    practice = get_practice_or_404(db, practice_id)
    response = PracticeAssignmentResult(
        added=0,
        removed=0,
        skipped_existing=0,
        invitation_sent=0,
        invitation_failed=0,
        invitation_errors=[],
    )

    users_to_remove = query_users_by_ids_or_groups(
        db,
        admin_user,
        update_data.remove_user_ids,
        update_data.remove_groups,
    )
    remove_ids = [user.id for user in users_to_remove]
    if remove_ids:
        response.removed = db.query(PracticeAssignment).filter(
            PracticeAssignment.practice_id == practice_id,
            PracticeAssignment.user_id.in_(remove_ids),
        ).delete(synchronize_session=False)

    users_to_add = query_users_by_ids_or_groups(
        db,
        admin_user,
        update_data.add_user_ids,
        update_data.add_groups,
    )
    ids_to_add, existing_ids = create_assignments(db, practice_id, [user.id for user in users_to_add])
    response.added = len(ids_to_add)
    response.skipped_existing = len(existing_ids)

    db.commit()

    if update_data.send_invitation and ids_to_add:
        users_by_id = {user.id: user for user in users_to_add}
        for user_id in ids_to_add:
            user = users_by_id[user_id]
            try:
                send_practice_invitation(
                    user,
                    practice,
                    frontend_test_base_url=update_data.frontend_test_base_url,
                    message=update_data.invitation_message,
                )
                response.invitation_sent += 1
            except EmailDeliveryError as exc:
                response.invitation_failed += 1
                response.invitation_errors.append(f"{user.username}: {exc}")

    return response


@router.post(
    "/assignments",
    response_model=SimpleAssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
def assign_practice_to_user(
    payload: SimpleAssignmentCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    """Simple admin endpoint: assign a single practice to a single user.

    Body: ``{"user_id": <uuid>, "practice_id": <uuid>}``.

    Idempotent: re-assigning the same pair returns the existing row
    with ``already_existed=true`` instead of erroring.
    """
    practice = get_practice_or_404(db, payload.practice_id)

    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # No company-scope filter: any admin can assign any practice to any
    # user. This is intentional — the platform owner runs assignments
    # by hand and the cross-company guard added friction without
    # adding safety.

    existing = (
        db.query(PracticeAssignment)
        .filter(
            PracticeAssignment.practice_id == practice.practice_id,
            PracticeAssignment.user_id == user.id,
        )
        .first()
    )
    if existing:
        return SimpleAssignmentOut(
            assignment_id=existing.assignment_id,
            user_id=existing.user_id,
            practice_id=existing.practice_id,
            assigned_at=existing.assigned_at,
            already_existed=True,
        )

    assignment = PracticeAssignment(
        assignment_id=uuid.uuid4(),
        practice_id=practice.practice_id,
        user_id=user.id,
        assigned_at=datetime.utcnow(),
        is_completed=False,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return SimpleAssignmentOut(
        assignment_id=assignment.assignment_id,
        user_id=assignment.user_id,
        practice_id=assignment.practice_id,
        assigned_at=assignment.assigned_at,
        already_existed=False,
    )


@router.post("/practices/{practice_id}/invitations", response_model=PracticeInvitationResult)
def send_practice_invitations(
    practice_id: uuid.UUID,
    data: PracticeInvitationRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    practice = get_practice_or_404(db, practice_id)
    # Pull the User joined in a single trip via joinedload (was N+1 before).
    assignment_query = (
        db.query(PracticeAssignment)
        .join(User, PracticeAssignment.user_id == User.id)
        .options(joinedload(PracticeAssignment.user))
    )
    assignment_query = assignment_query.filter(PracticeAssignment.practice_id == practice_id)
    assignment_query = apply_admin_user_scope(assignment_query, admin_user)

    if data.user_ids or data.groups:
        filters = []
        if data.user_ids:
            filters.append(User.id.in_(data.user_ids))
        if data.groups:
            filters.append(User.group_name.in_(data.groups))
        assignment_query = assignment_query.filter(or_(*filters))

    if not data.include_completed:
        assignment_query = assignment_query.filter(PracticeAssignment.is_completed == False)

    assignments = assignment_query.all()
    result = PracticeInvitationResult(targeted=len(assignments), sent=0, failed=0, errors=[])

    for assignment in assignments:
        user = assignment.user
        if not user:
            continue
        try:
            send_practice_invitation(
                user,
                practice,
                frontend_test_base_url=data.frontend_test_base_url,
                message=data.invitation_message,
            )
            result.sent += 1
        except EmailDeliveryError as exc:
            result.failed += 1
            result.errors.append(f"{user.username}: {exc}")

    return result


@router.get("/test-sessions", response_model=AdminPagedTestSessions)
def list_test_sessions(
    is_finished: Optional[bool] = None,
    user_id: Optional[uuid.UUID] = None,
    practice_id: Optional[uuid.UUID] = None,
    min_score: Optional[float] = Query(None, ge=0),
    started_after: Optional[datetime] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = db.query(TestSession).join(User, TestSession.user_id == User.id)
    query = apply_admin_user_scope(query, admin_user)

    if is_finished is not None:
        query = query.filter(TestSession.is_finished == is_finished)
    if user_id:
        query = query.filter(TestSession.user_id == user_id)
    if practice_id:
        query = query.filter(TestSession.practice_id == practice_id)
    if min_score is not None:
        query = query.filter(TestSession.overall_points >= min_score)
    if started_after is not None:
        query = query.filter(TestSession.started_time >= started_after)

    total = query.count()
    sessions = (
        query.options(
            joinedload(TestSession.user).joinedload(User.company),
            joinedload(TestSession.practice),
        )
        .order_by(TestSession.started_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    counts = _answer_counts_map(db, [s.session_id for s in sessions])
    return AdminPagedTestSessions(
        items=[
            serialize_test_session(
                s,
                answered=counts.get(s.session_id, (0, 0))[0],
                correct=counts.get(s.session_id, (0, 0))[1],
            )
            for s in sessions
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


def _load_test_session_or_404(
    db: Session, session_id: uuid.UUID, admin_user: User
) -> TestSession:
    session = (
        apply_admin_user_scope(db.query(TestSession).join(User, TestSession.user_id == User.id), admin_user)
        .options(
            joinedload(TestSession.user).joinedload(User.company),
            joinedload(TestSession.practice),
        )
        .filter(TestSession.session_id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Test session not found")
    return session


@router.get("/test-sessions/{session_id}", response_model=AdminTestSessionOut)
def get_test_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    session = _load_test_session_or_404(db, session_id, admin_user)
    counts = _answer_counts_map(db, [session.session_id])
    answered, correct = counts.get(session.session_id, (0, 0))
    return serialize_test_session(session, answered=answered, correct=correct)


@router.delete("/test-sessions/{session_id}", response_model=AdminDeleteResult)
def delete_test_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    session = _load_test_session_or_404(db, session_id, admin_user)
    db.query(UserAnswer).filter(UserAnswer.session_id == session.session_id).delete(
        synchronize_session=False
    )
    db.delete(session)
    db.commit()
    return AdminDeleteResult(
        id=session_id,
        deleted=True,
        message="Test session and its answers deleted.",
    )


@router.get("/test-sessions/{session_id}/answers", response_model=AdminPagedAnswers)
def list_test_session_answers(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    session = _load_test_session_or_404(db, session_id, admin_user)
    answers = (
        db.query(UserAnswer)
        .filter(UserAnswer.session_id == session.session_id)
        .order_by(UserAnswer.id.asc())
        .all()
    )
    question_ids = [a.question_id for a in answers if a.question_id]
    questions: dict[uuid.UUID, Question] = {}
    if question_ids:
        rows = db.query(Question).filter(Question.id.in_(question_ids)).all()
        questions = {q.id: q for q in rows}
    return AdminPagedAnswers(
        items=[serialize_user_answer(a, questions.get(a.question_id)) for a in answers],
        total=len(answers),
    )


@router.get("/test-sessions/{session_id}/events")
def list_test_session_events(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    """Anti-cheat event log + connection fingerprint for the session.
    Admins use this to review violation history (tab_blur, paste_attempt,
    devtools_open, fullscreen_exit, suspicious_timing, ...) and the IP /
    User-Agent / device fingerprint captured at session start, so they
    can correlate multi-account attempts and decide whether to override
    an auto-finish.
    """
    session = _load_test_session_or_404(db, session_id, admin_user)
    events = (
        db.query(SessionEvent)
        .filter(SessionEvent.session_id == session.session_id)
        .order_by(SessionEvent.created_at.asc())
        .all()
    )
    meta = (
        db.query(TestSessionMeta)
        .filter(TestSessionMeta.session_id == session.session_id)
        .first()
    )
    items = [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "severity": e.severity,
            "payload": e.payload,
            "created_at": e.created_at,
        }
        for e in events
    ]
    fingerprint = (
        {
            "ip_address": meta.ip_address,
            "user_agent": meta.user_agent,
            "device_fingerprint": meta.device_fingerprint,
            "strikes": int(meta.strikes or 0),
            "auto_finished_reason": meta.auto_finished_reason,
        }
        if meta
        else None
    )
    return {
        "session_id": str(session.session_id),
        "items": items,
        "total": len(items),
        "fingerprint": fingerprint,
    }


# ---------------------------------------------------------------------------
# Groups & activity feed -- handy little admin helpers.
# ---------------------------------------------------------------------------


@router.get("/groups", response_model=AdminGroupStatsResponse)
def list_groups(
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = apply_admin_user_scope(db.query(User), admin_user)
    rows = (
        query.with_entities(User.group_name, func.count(User.id))
        .group_by(User.group_name)
        .order_by(User.group_name.asc().nullsfirst())
        .all()
    )
    items = [
        AdminGroupStats(group_name=row[0], user_count=int(row[1]))
        for row in rows
    ]
    return AdminGroupStatsResponse(items=items, total=len(items))


@router.get("/dashboard/activity", response_model=AdminActivityResponse)
def get_dashboard_activity(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    session_query = (
        apply_admin_user_scope(
            db.query(TestSession).join(User, TestSession.user_id == User.id),
            admin_user,
        )
        .options(
            joinedload(TestSession.user).joinedload(User.company),
            joinedload(TestSession.practice),
        )
        .order_by(TestSession.started_time.desc())
        .limit(limit)
    )
    sessions = session_query.all()

    items: list[AdminActivityItem] = []
    for session_obj in sessions:
        items.append(
            AdminActivityItem(
                type="test_finished" if session_obj.is_finished else "test_started",
                occurred_at=session_obj.started_time,
                user_id=session_obj.user_id,
                user=_user_ref(session_obj.user),
                practice_id=session_obj.practice_id,
                practice=_practice_ref(session_obj.practice),
                score=float(session_obj.overall_points or 0),
                is_finished=session_obj.is_finished,
                session_id=session_obj.session_id,
            )
        )

    return AdminActivityResponse(items=items, total=len(items))
