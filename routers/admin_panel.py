import secrets
import string
import uuid
from datetime import datetime
from html import escape
from typing import List, Optional, Sequence

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
    TestSession,
    User,
    UserAnswer,
)
from routers.login import get_current_user
from schemas.user_schema import (
    AdminBulkUserCreate,
    AdminBulkUserCreateResponse,
    AdminCandidateOut,
    AdminDashboardSummary,
    AdminStudentStatsResponse,
    AdminTestSessionOut,
    AdminUserAnswerOut,
    AdminUserCreate,
    AdminUserCreatedOut,
    AdminUserOut,
    AdminUserSearchResponse,
    AdminVacancyCreate,
    AdminVacancyOut,
    AdminVacancyUpdate,
    AdvancedAssignmentUpdate,
    CandidateStatusUpdate,
    CompanyOut,
    DifficultyUpdate,
    PracticeAssignmentOut,
    PracticeAssignmentResult,
    PracticeCreate,
    PracticeInvitationRequest,
    PracticeInvitationResult,
    PracticeOut,
    PracticeUpdate,
    QuestionCreate,
    QuestionHistoryOut,
    QuestionOptionCreate,
    QuestionOut,
    QuestionUpdate,
)
from utils.mailer import EmailDeliveryError, send_email


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


@router.get("/users", response_model=List[AdminUserOut])
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

    return query.order_by(User.username.asc()).offset(offset).limit(limit).all()


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
    users = query.order_by(User.username.asc()).offset(offset).limit(limit).all()
    return {"items": users, "total": total, "offset": offset, "limit": limit}


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

    # Pre-fetch all potentially conflicting users in two queries (one for
    # usernames, one for emails) instead of issuing 2 SELECTs per row.
    requested_usernames = {item.username for item in data.users if item.username}
    requested_emails = {str(item.email) for item in data.users if item.email}

    username_map: dict[str, User] = {}
    if requested_usernames:
        rows = (
            db.query(User)
            .filter(User.username.in_(requested_usernames))
            .all()
        )
        username_map = {u.username: u for u in rows}

    email_map: dict[str, User] = {}
    if requested_emails:
        rows = (
            db.query(User)
            .filter(User.email.in_(requested_emails))
            .all()
        )
        email_map = {u.email: u for u in rows}

    for item in data.users:
        existing = None
        if item.username:
            existing = username_map.get(item.username)
        if not existing:
            existing = email_map.get(str(item.email))

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

        username = item.username or generate_unique_username(
            item.name,
            item.surname,
            db,
            reserved=reserved_usernames,
        )
        if username in reserved_usernames or db.query(User.id).filter(User.username == username).first():
            failed.append({"email": str(item.email), "reason": "Username already exists."})
            continue

        reserved_usernames.add(username)
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


@router.get("/users/{user_id}", response_model=AdminUserOut)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    user = apply_admin_user_scope(db.query(User), admin_user).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/companies", response_model=List[CompanyOut])
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

    return query.order_by(Company.name.asc()).offset(offset).limit(limit).all()


@router.get("/companies/{company_id}", response_model=CompanyOut)
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
    return company


@router.get("/companies/{company_id}/users", response_model=List[AdminUserOut])
def list_company_users(
    company_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    if admin_user.role != Role.SUPERADMIN and admin_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Company is outside this admin's scope.")

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
    admin_user: User = Depends(require_admin),
):
    if admin_user.role != Role.SUPERADMIN and admin_user.company_id != company_id:
        raise HTTPException(status_code=403, detail="Company is outside this admin's scope.")

    return (
        db.query(Created_Vacancy)
        .filter(Created_Vacancy.company_id == company_id)
        .order_by(Created_Vacancy.start_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/vacancies", response_model=List[AdminVacancyOut])
def list_vacancies(
    company_id: Optional[uuid.UUID] = None,
    is_available: Optional[bool] = None,
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

    return query.order_by(Created_Vacancy.start_date.desc()).offset(offset).limit(limit).all()


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

    vacancy = Created_Vacancy(
        id=uuid.uuid4(),
        job_name=data.job_name,
        job_description=data.job_description,
        tag=data.tag,
        start_date=data.start_date,
        end_date=data.end_date,
        company_id=company_id,
        is_available=data.is_available,
    )
    db.add(vacancy)
    db.commit()
    db.refresh(vacancy)
    return vacancy


@router.get("/vacancies/{vacancy_id}", response_model=AdminVacancyOut)
def get_vacancy(
    vacancy_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    vacancy = apply_admin_vacancy_scope(db.query(Created_Vacancy), admin_user).filter(
        Created_Vacancy.id == vacancy_id
    ).first()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    return vacancy


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

    start_date = update_data.get("start_date", vacancy.start_date)
    end_date = update_data.get("end_date", vacancy.end_date)
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date.")

    for field, value in update_data.items():
        setattr(vacancy, field, value)

    db.commit()
    db.refresh(vacancy)
    return vacancy


@router.get("/vacancies/{vacancy_id}/candidates", response_model=List[AdminCandidateOut])
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

    return query.order_by(Candidate.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/candidates", response_model=List[AdminCandidateOut])
def list_candidates(
    status_filter: Optional[str] = Query(None, alias="status"),
    vacancy_id: Optional[uuid.UUID] = None,
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
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Candidate.full_name.ilike(pattern), Candidate.skills.ilike(pattern)))

    return query.order_by(Candidate.created_at.desc()).offset(offset).limit(limit).all()


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

    candidate.status = update_data.status
    db.commit()
    db.refresh(candidate)
    return candidate


@router.get("/questions")
def list_questions(
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    query = db.query(Question)

    if category:
        query = query.filter(Question.category == category)
    if search:
        query = query.filter(Question.text.ilike(f"%{search}%"))

    questions = query.order_by(Question.category.asc(), Question.difficulty_level.asc()).offset(offset).limit(limit).all()
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


@router.patch("/questions/{question_id}/difficulty")
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
    admin_user: User = Depends(require_admin),
):
    return (
        db.query(QuestionHistory)
        .filter(QuestionHistory.question_id == question_id)
        .order_by(QuestionHistory.changed_at.desc())
        .all()
    )


@router.get("/practices", response_model=List[PracticeOut])
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

    return query.order_by(Practice.created_at.desc()).offset(offset).limit(limit).all()


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
    return new_practice


@router.get("/practices/{practice_id}", response_model=PracticeOut)
def get_practice(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    return get_practice_or_404(db, practice_id)


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
    return practice


@router.get("/practices/{practice_id}/assignments", response_model=List[PracticeAssignmentOut])
def list_practice_assignments(
    practice_id: uuid.UUID,
    is_completed: Optional[bool] = None,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    get_practice_or_404(db, practice_id)
    query = (
        db.query(PracticeAssignment)
        .join(User, PracticeAssignment.user_id == User.id)
        .options(joinedload(PracticeAssignment.user))
    )
    query = query.filter(PracticeAssignment.practice_id == practice_id)
    query = apply_admin_user_scope(query, admin_user)

    if is_completed is not None:
        query = query.filter(PracticeAssignment.is_completed == is_completed)

    return query.order_by(PracticeAssignment.assigned_at.desc()).all()


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


@router.get("/test-sessions", response_model=List[AdminTestSessionOut])
def list_test_sessions(
    is_finished: Optional[bool] = None,
    user_id: Optional[uuid.UUID] = None,
    practice_id: Optional[uuid.UUID] = None,
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

    return query.order_by(TestSession.started_time.desc()).offset(offset).limit(limit).all()


@router.get("/test-sessions/{session_id}", response_model=AdminTestSessionOut)
def get_test_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    session = (
        apply_admin_user_scope(db.query(TestSession).join(User, TestSession.user_id == User.id), admin_user)
        .filter(TestSession.session_id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Test session not found")
    return session


@router.get("/test-sessions/{session_id}/answers", response_model=List[AdminUserAnswerOut])
def list_test_session_answers(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    session = get_test_session(session_id, db, admin_user)
    return (
        db.query(UserAnswer)
        .filter(UserAnswer.session_id == session.session_id)
        .order_by(UserAnswer.id.asc())
        .all()
    )
