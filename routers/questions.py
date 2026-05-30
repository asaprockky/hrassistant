import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy import Integer, and_, func
from sqlalchemy.orm import Session, joinedload

from database.database import get_db
from database.models import (
    Practice,
    PracticeAssignment,
    Question,
    SessionEvent,
    TestSession,
    TestSessionMeta,
    UserAnswer,
    UserSkill,
)
from routers.login import get_current_user
from schemas.user_schema import (
    AnswerCreate,
    SessionEventCreate,
    SessionStartRequest,
)
from utils.ai_logic import calculate_difficulty_score


# ==========================================
# ANTI-CHEAT CONFIG
# ==========================================

# A `warn` or `critical` event consumes a strike. The first two strikes
# return an escalating warning to the client ("Warning 1 of 3" /
# "Warning 2 of 3"); the third auto-finishes the session with
# reason="cheating_detected". Set to 1 if you want zero-tolerance.
# This is the single source of truth for the threshold — the frontend
# never hard-codes a number, it always reads `strike_limit` from the
# /events response.
STRIKE_LIMIT = 3

# Answers submitted faster than this are auto-flagged as suspicious_timing.
SUSPICIOUS_TIMING_SECONDS = 0.5

# These events are hard policy failures. They immediately close the
# session with `reason=cheating_detected` and a zero score.
#
# Everything else goes through the normal strike counter (two warnings,
# then close on the third violation — see STRIKE_LIMIT) so a noisy OS
# notification or stray ESC press doesn't zero a student out without
# warning. Mobile / multi-display are the only events we never warn on
# because they describe a setup that is fundamentally incompatible with
# a proctored test.
IMMEDIATE_ZERO_SCORE_EVENTS = {
    "multiple_displays_suspected",
    "mobile_device_blocked",
}

MOBILE_UA_MARKERS = (
    "android",
    "iphone",
    "ipod",
    "ipad",
    "mobile",
    "windows phone",
    "opera mini",
)

# Skill estimate update rate. Higher = more responsive but noisier.
SKILL_K = 0.12

# How sharply the expected score curve responds to skill - difficulty gap.
SKILL_LOGISTIC_SCALE = 4.0


router = APIRouter(prefix="/testing", tags=["Testing"])


# ==========================================
# HELPERS
# ==========================================

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _practice_or_404(db: Session, practice_id: uuid.UUID) -> Practice:
    practice = (
        db.query(Practice).filter(Practice.practice_id == practice_id).first()
    )
    if not practice or not practice.is_valid:
        raise HTTPException(status_code=404, detail="Practice not found")
    return practice


def _session_owned_or_404(
    db: Session, session_id: uuid.UUID, user_id: uuid.UUID
) -> TestSession:
    session = (
        db.query(TestSession)
        .options(joinedload(TestSession.practice))
        .filter(TestSession.session_id == session_id)
        .first()
    )
    if not session or session.user_id != user_id:
        # Don't disclose existence of other users' sessions.
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _total_weight_for(db: Session, practice: Practice) -> float:
    if not practice.question_ids:
        return 1.0
    total = (
        db.query(func.sum(Question.points))
        .filter(Question.id.in_(practice.question_ids))
        .scalar()
    )
    return float(total or 1.0)


def _deadline_exceeded(session: TestSession, practice: Practice) -> bool:
    if not practice.duration_minutes:
        return False
    started = session.started_time or _utcnow()
    cutoff = started + timedelta(minutes=practice.duration_minutes)
    return _utcnow() > cutoff


def _finish_session(
    db: Session,
    session: TestSession,
    *,
    reason: Optional[str] = None,
    final_score: Optional[float] = None,
) -> TestSession:
    """Idempotent finalize: marks the session finished and the matching
    PracticeAssignment completed. Safe to call multiple times.

    When `reason` is provided (e.g. "abandoned", "cheating_detected",
    "duration_exceeded") and the meta row exists, it is recorded on
    `TestSessionMeta.auto_finished_reason` so admins can tell why the
    session was auto-closed.
    """
    if session.is_finished:
        return session

    if final_score is not None:
        session.overall_points = final_score

    session.is_finished = True

    if reason:
        meta = (
            db.query(TestSessionMeta)
            .filter(TestSessionMeta.session_id == session.session_id)
            .first()
        )
        if meta is not None and not meta.auto_finished_reason:
            meta.auto_finished_reason = reason[:64]

    assignment = (
        db.query(PracticeAssignment)
        .filter(
            PracticeAssignment.practice_id == session.practice_id,
            PracticeAssignment.user_id == session.user_id,
        )
        .first()
    )
    if assignment and not assignment.is_completed:
        assignment.is_completed = True
        assignment.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(session)
    return session


def _session_progress(db: Session, session: TestSession) -> dict:
    practice = session.practice or _practice_or_404(db, session.practice_id)
    total_q = len(practice.question_ids) if practice.question_ids else 0
    answered = (
        db.query(func.count(UserAnswer.id))
        .filter(UserAnswer.session_id == session.session_id)
        .scalar()
    ) or 0
    correct = (
        db.query(func.count(UserAnswer.id))
        .filter(
            UserAnswer.session_id == session.session_id,
            UserAnswer.is_correct == True,
        )
        .scalar()
    ) or 0

    started = session.started_time
    duration_min = practice.duration_minutes or 0
    if started and duration_min:
        ends_at = started + timedelta(minutes=duration_min)
        seconds_remaining = max(0, int((ends_at - _utcnow()).total_seconds()))
    else:
        ends_at = None
        seconds_remaining = None

    return {
        "session_id": str(session.session_id),
        "practice_id": str(session.practice_id),
        "is_finished": session.is_finished,
        "answered_count": int(answered),
        "correct_count": int(correct),
        "total_questions": total_q,
        "overall_points": round(float(session.overall_points or 0.0), 2),
        "started_at": started,
        "ends_at": ends_at,
        "seconds_remaining": seconds_remaining,
    }


# ==========================================
# ANTI-CHEAT + ADAPTIVE DIFFICULTY HELPERS
# ==========================================

def _get_or_create_meta(db: Session, session: TestSession) -> TestSessionMeta:
    """Return the TestSessionMeta sidecar for this session, creating an
    empty row if missing (legacy sessions don't have one). Caller is
    responsible for committing."""
    meta = (
        db.query(TestSessionMeta)
        .filter(TestSessionMeta.session_id == session.session_id)
        .first()
    )
    if meta is None:
        meta = TestSessionMeta(session_id=session.session_id, strikes=0)
        db.add(meta)
        db.flush()
    return meta


def _get_user_skill(db: Session, user_id: uuid.UUID) -> float:
    """Read the user's running skill estimate (0..1), defaulting to 0.5
    when no row exists yet."""
    row = (
        db.query(UserSkill.skill_estimate)
        .filter(UserSkill.user_id == user_id)
        .first()
    )
    if row is None or row[0] is None:
        return 0.5
    return float(row[0])


def _update_user_skill(
    db: Session, user_id: uuid.UUID, question_difficulty: float, is_correct: bool
) -> float:
    """Bump the user's skill estimate after an answer. Uses a simple
    logistic-Elo: expected = sigmoid((skill - difficulty) * scale);
    delta = K * (actual - expected). Returns the new clamped value."""
    current = _get_user_skill(db, user_id)
    difficulty = float(question_difficulty or 0.5)
    try:
        expected = 1.0 / (
            1.0 + math.exp(-SKILL_LOGISTIC_SCALE * (current - difficulty))
        )
    except OverflowError:
        expected = 0.0 if (current - difficulty) < 0 else 1.0
    actual = 1.0 if is_correct else 0.0
    new_skill = max(0.0, min(1.0, current + SKILL_K * (actual - expected)))

    row = db.query(UserSkill).filter(UserSkill.user_id == user_id).first()
    if row is None:
        row = UserSkill(
            user_id=user_id, skill_estimate=new_skill, updated_at=datetime.utcnow()
        )
        db.add(row)
    else:
        row.skill_estimate = new_skill
        row.updated_at = datetime.utcnow()
    db.flush()
    return new_skill


def _pick_adaptive_question(
    db: Session,
    session: TestSession,
    practice: Practice,
    user_skill: float,
) -> tuple[Optional[Question], list, int]:
    """Pick the unanswered question whose `difficulty_level` is closest
    to the user's current skill estimate. Falls back to the locked
    `TestSessionMeta.question_order` if present, otherwise to
    `Practice.question_ids`. Tie-breaks by UUID string for stable
    resume behaviour."""
    answered_ids = {
        row[0]
        for row in db.query(UserAnswer.question_id)
        .filter(UserAnswer.session_id == session.session_id)
        .all()
    }
    meta = session.meta if hasattr(session, "meta") else None
    order_source = (
        list(meta.question_order)
        if meta is not None and meta.question_order
        else list(practice.question_ids or [])
    )
    remaining_ids = [q for q in order_source if q not in answered_ids]
    total = len(order_source)
    answered_count = total - len(remaining_ids)

    if not remaining_ids:
        return None, [], answered_count

    qs_by_id = {
        q.id: q
        for q in db.query(Question).filter(Question.id.in_(remaining_ids)).all()
    }
    candidates = [qs_by_id[qid] for qid in remaining_ids if qid in qs_by_id]
    if not candidates:
        return None, remaining_ids, answered_count

    candidates.sort(
        key=lambda q: (abs(float(q.difficulty_level or 0.5) - user_skill), str(q.id))
    )
    return candidates[0], remaining_ids, answered_count


def _extract_client_metadata(request: Optional[Request]) -> dict:
    """Best-effort capture of the client's IP and User-Agent. Honours
    `X-Forwarded-For` when set by a reverse proxy."""
    if request is None:
        return {"ip_address": None, "user_agent": None}
    fwd = request.headers.get("x-forwarded-for") or ""
    ip = fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else None
    )
    ua = request.headers.get("user-agent")
    if ua and len(ua) > 1024:
        ua = ua[:1024]
    return {"ip_address": ip, "user_agent": ua}


def _is_mobile_user_agent(user_agent: Optional[str]) -> bool:
    ua = (user_agent or "").lower()
    return any(marker in ua for marker in MOBILE_UA_MARKERS)


def _format_answers(db: Session, session: TestSession) -> list:
    rows = (
        db.query(UserAnswer)
        .filter(UserAnswer.session_id == session.session_id)
        .order_by(UserAnswer.id.asc())
        .all()
    )
    if not rows:
        return []
    qids = list({r.question_id for r in rows if r.question_id})
    qs_by_id = (
        {q.id: q for q in db.query(Question).filter(Question.id.in_(qids)).all()}
        if qids
        else {}
    )
    items = []
    for r in rows:
        q = qs_by_id.get(r.question_id) if r.question_id else None
        items.append(
            {
                "id": str(r.id),
                "question_id": str(r.question_id) if r.question_id else None,
                "question_text": q.text if q else None,
                "user_answer": r.user_answer,
                "is_correct": r.is_correct,
                "correct_answer_id": str(q.correct_answer) if q and q.correct_answer else None,
                "points_awarded": round(float(r.points_awarded or 0.0), 2),
                "time_spent": r.time_spent,
            }
        )
    return items


# ==========================================
# 1. PRACTICE / ELIGIBILITY (read-only, pre-test)
# ==========================================

@router.get("/practices/{practice_id}")
def get_practice_info(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Practice metadata for the candidate's test page.

    Does NOT include the questions themselves — those are streamed via
    `/sessions/{id}/next-question` so we don't leak the question bank before
    the user has actually started.
    """
    practice = _practice_or_404(db, practice_id)
    return {
        "practice_id": str(practice.practice_id),
        "title": practice.title,
        "description": practice.description or "",
        "duration_minutes": practice.duration_minutes,
        "deadline": practice.deadline,
        "question_count": len(practice.question_ids) if practice.question_ids else 0,
        "tags": practice.tags or [],
    }


@router.get("/practices/{practice_id}/eligibility")
def get_practice_eligibility(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns whether the current user can start the practice, or
    whether their single attempt has already been used.

    Strict no-resume policy: a candidate gets exactly one attempt.
    `in_progress` is NOT a resumable state — it means the candidate
    started, then left, and the session is still flagged in-progress
    in the DB only because the abandon beacon didn't reach the server.
    The client treats `in_progress` exactly like `finished` (no resume,
    locked) and explicitly finalizes the orphan session via
    `POST /sessions/{id}/abandon` before showing the report.

    This endpoint is strictly READ-ONLY — calling it must never mutate
    session state. (Mutation here caused a race with the post-start
    refetch and closed the session the user had just opened.)

    Response `status` values:
      - `not_found`            — practice doesn't exist or is invalidated
      - `not_invited`          — user has no PracticeAssignment for this practice
      - `assignment_completed` — assignment is marked completed (no session yet,
                                 e.g. set by an admin)
      - `deadline_passed`      — practice deadline is in the past
      - `finished`             — a finished TestSession already exists
      - `duration_exceeded`    — an in-progress session's timer has expired;
                                 the next call to /next-question will
                                 finalize it
      - `in_progress`          — an attempt was started and left; the
                                 client must finalize it via /abandon
                                 (no resume path)
      - `eligible`             — user can call POST /sessions to start

    `can_resume` is ALWAYS false. It is kept on the response shape for
    backwards compatibility with older clients but no longer signals
    a real resume path.
    """
    practice = (
        db.query(Practice).filter(Practice.practice_id == practice_id).first()
    )
    if not practice or not practice.is_valid:
        return {
            "status": "not_found",
            "can_start": False,
            "can_resume": False,
            "session_id": None,
            "reason": "Practice not found.",
        }

    assignment = (
        db.query(PracticeAssignment)
        .filter(
            PracticeAssignment.practice_id == practice_id,
            PracticeAssignment.user_id == current_user.id,
        )
        .first()
    )
    if not assignment:
        return {
            "status": "not_invited",
            "can_start": False,
            "can_resume": False,
            "session_id": None,
            "reason": "You are not invited to this test.",
        }

    existing = (
        db.query(TestSession)
        .filter(
            TestSession.user_id == current_user.id,
            TestSession.practice_id == practice_id,
        )
        .first()
    )
    if existing:
        if existing.is_finished:
            return {
                "status": "finished",
                "can_start": False,
                "can_resume": False,
                "session_id": str(existing.session_id),
                "reason": "You have already completed this assessment.",
            }
        if _deadline_exceeded(existing, practice):
            # Do NOT mutate here — next-question / submit-answer will
            # finalize the session on the next interaction. Eligibility
            # is informational only.
            return {
                "status": "duration_exceeded",
                "can_start": False,
                "can_resume": False,
                "session_id": str(existing.session_id),
                "reason": "Test duration has expired.",
            }
        # In-progress session that the candidate left without the
        # abandon beacon completing. Per strict no-resume policy this
        # is NOT resumable. `can_resume` is False so any older client
        # that still checks the flag falls through to the locked UI.
        # New clients explicitly finalize the orphan via /abandon
        # before redirecting to the report.
        return {
            "status": "in_progress",
            "can_start": False,
            "can_resume": False,
            "session_id": str(existing.session_id),
            "reason": "You have already used your attempt for this assessment.",
        }

    if assignment.is_completed:
        return {
            "status": "assignment_completed",
            "can_start": False,
            "can_resume": False,
            "session_id": None,
            "reason": "Assignment is already marked completed.",
        }

    if practice.deadline and practice.deadline < _utcnow():
        return {
            "status": "deadline_passed",
            "can_start": False,
            "can_resume": False,
            "session_id": None,
            "reason": "Practice deadline has passed.",
        }

    return {
        "status": "eligible",
        "can_start": True,
        "can_resume": False,
        "session_id": None,
        "reason": None,
    }


@router.get("/practices/{practice_id}/result")
def get_test_result(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns the user's latest test session score for a practice."""
    user_id = current_user.id

    assignment = (
        db.query(PracticeAssignment)
        .filter(
            PracticeAssignment.practice_id == practice_id,
            PracticeAssignment.user_id == user_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=403, detail="You are not invited to this test.")

    session = (
        db.query(TestSession)
        .filter(
            TestSession.user_id == user_id,
            TestSession.practice_id == practice_id,
        )
        .order_by(TestSession.started_time.desc())
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="No session found")

    return {
        "practice_id": practice_id,
        "session_id": str(session.session_id),
        "total_score": round(float(session.overall_points or 0.0), 2),
        "is_finished": session.is_finished,
        "started_at": session.started_time,
    }


@router.get("/assignments/{filter_option}")
def get_assigned_tests(
    filter_option: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lists practices the user is invited to and hasn't yet attempted.

    `filter_option` may be `latest`, `all`, or a positive integer limit.
    """
    now = _utcnow()

    sql_limit: Optional[int] = None
    if filter_option == "latest":
        sql_limit = 1
    elif filter_option == "all":
        sql_limit = None
    else:
        try:
            sql_limit = int(filter_option)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid filter option.")

    query = (
        db.query(Practice)
        .join(PracticeAssignment, Practice.practice_id == PracticeAssignment.practice_id)
        .outerjoin(
            TestSession,
            and_(
                TestSession.practice_id == Practice.practice_id,
                TestSession.user_id == current_user.id,
            ),
        )
        .filter(
            PracticeAssignment.user_id == current_user.id,
            Practice.is_valid == True,
            Practice.deadline > now,
            PracticeAssignment.is_completed == False,
            TestSession.session_id == None,
        )
        .order_by(Practice.deadline.asc())
    )

    if sql_limit is not None:
        query = query.limit(sql_limit)

    def format_assessment(p: Practice):
        return {
            "practiceId": str(p.practice_id),
            "title": p.title,
            "type": "pending",
            "dueDate": p.deadline.isoformat() if p.deadline else None,
            "duration": f"{p.duration_minutes} min",
            "questionQuantity": len(p.question_ids) if p.question_ids else 0,
        }

    practices = query.all()
    results = [format_assessment(p) for p in practices]

    if filter_option == "latest":
        return results[0] if results else None
    return results


# ==========================================
# 2. SESSION LIFECYCLE (HTTP replacement for the legacy WebSocket)
# ==========================================

@router.post(
    "/practices/{practice_id}/sessions",
    status_code=status.HTTP_201_CREATED,
)
def start_session(
    practice_id: uuid.UUID,
    request: Request,
    body: Optional[SessionStartRequest] = Body(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Creates a new TestSession for the current user against a practice.

    Anti-cheat side effects (sidecar `test_session_meta` row):
      - snapshot+shuffle `Practice.question_ids` so the order is locked
        to this session, defeats memorising the question pool, and
        survives a refresh;
      - capture IP / User-Agent / optional device_fingerprint so an admin
        can correlate multi-account / shared-session attempts.

    Same invitation / completion / re-entry / deadline checks as before.
    Returns 409 with the existing session id when a session already
    exists so clients can resume.
    """
    practice = _practice_or_404(db, practice_id)

    assignment = (
        db.query(PracticeAssignment)
        .filter(
            PracticeAssignment.practice_id == practice_id,
            PracticeAssignment.user_id == current_user.id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=403, detail="You are not invited to this test.")
    if assignment.is_completed:
        raise HTTPException(status_code=409, detail="This assignment is already completed.")

    existing = (
        db.query(TestSession)
        .filter(
            TestSession.user_id == current_user.id,
            TestSession.practice_id == practice_id,
        )
        .first()
    )
    if existing:
        # No-resume policy: any prior session — finished or abandoned —
        # consumes the user's attempt. If we ever find one in flight
        # here (race with the abandon beacon) close it before bailing
        # so the UI doesn't render a stale "in progress" state.
        if not existing.is_finished:
            _finish_session(db, existing, reason="abandoned")
        raise HTTPException(
            status_code=409,
            detail={
                "message": "You have already attempted this test. Speak to your admin to be re-assigned.",
                "session_id": str(existing.session_id),
                "is_finished": True,
            },
        )

    now = _utcnow()
    if practice.deadline and practice.deadline < now:
        raise HTTPException(status_code=409, detail="Practice deadline has passed.")

    meta_client = _extract_client_metadata(request)
    if _is_mobile_user_agent(meta_client["user_agent"]):
        raise HTTPException(
            status_code=403,
            detail="Tests must be taken from a desktop or laptop browser.",
        )

    session = TestSession(
        session_id=uuid.uuid4(),
        practice_id=practice_id,
        user_id=current_user.id,
        overall_points=0.0,
        is_finished=False,
        started_time=now,
    )
    db.add(session)
    db.flush()

    # Anti-cheat sidecar: shuffled question_order locked to this session
    # + connection fingerprint captured from the request.
    shuffled = list(practice.question_ids or [])
    random.shuffle(shuffled)
    device_fp = body.device_fingerprint if (body and body.device_fingerprint) else None
    meta = TestSessionMeta(
        session_id=session.session_id,
        question_order=shuffled,
        ip_address=meta_client["ip_address"],
        user_agent=meta_client["user_agent"],
        device_fingerprint=device_fp,
        strikes=0,
    )
    db.add(meta)
    db.commit()
    db.refresh(session)

    ends_at = (
        session.started_time + timedelta(minutes=practice.duration_minutes)
        if practice.duration_minutes
        else None
    )
    return {
        "event": "test_started",
        "session_id": str(session.session_id),
        "practice_id": str(practice.practice_id),
        "started_at": session.started_time,
        "duration_minutes": practice.duration_minutes,
        "ends_at": ends_at,
        "total_questions": len(practice.question_ids) if practice.question_ids else 0,
        # Legacy field names from the old WS payload so frontends that
        # already read `quantity` / `duration` keep working.
        "quantity": len(practice.question_ids) if practice.question_ids else 0,
        "duration": practice.duration_minutes,
    }


@router.get("/practices/{practice_id}/session")
def get_my_session_for_practice(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns the current user's TestSession (active or finished) for a
    practice if one exists, or `null` otherwise.

    Designed so the frontend can decide between "Start", "Resume", and
    "View result" without first attempting `POST /sessions`.
    """
    session = (
        db.query(TestSession)
        .options(joinedload(TestSession.practice))
        .filter(
            TestSession.user_id == current_user.id,
            TestSession.practice_id == practice_id,
        )
        .first()
    )
    if not session:
        return None
    return _session_progress(db, session)


@router.get("/sessions/{session_id}")
def get_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Snapshot of the session: timing, score, progress."""
    session = _session_owned_or_404(db, session_id, current_user.id)
    return _session_progress(db, session)


@router.get("/sessions/{session_id}/next-question")
def get_next_question(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns the next unanswered question for the session.

    Selection is adaptive: the question whose `difficulty_level` is
    closest to the user's running `UserSkill.skill_estimate` is served
    next. Order is drawn from the session's locked, shuffled
    `TestSessionMeta.question_order` (falls back to `Practice.question_ids`
    for legacy sessions created before the sidecar existed).

    Auto-finishes the session when all questions are answered or the
    timer has expired.

    Response is one of:
      - `{event: "question_data", ...}` — render the question
      - `{event: "test_finished", reason: "all_answered"|"duration_exceeded", ...}`
    """
    session = _session_owned_or_404(db, session_id, current_user.id)
    if session.is_finished:
        raise HTTPException(status_code=409, detail="Session is already finished.")

    practice = session.practice or _practice_or_404(db, session.practice_id)

    if _deadline_exceeded(session, practice):
        finished = _finish_session(db, session)
        return {
            "event": "test_finished",
            "session_id": str(finished.session_id),
            "final_score": round(float(finished.overall_points or 0.0), 2),
            "reason": "duration_exceeded",
        }

    user_skill = _get_user_skill(db, current_user.id)
    next_q, remaining_ids, answered_count = _pick_adaptive_question(
        db, session, practice, user_skill
    )

    if next_q is None:
        finished = _finish_session(db, session)
        return {
            "event": "test_finished",
            "session_id": str(finished.session_id),
            "final_score": round(float(finished.overall_points or 0.0), 2),
            "reason": "all_answered",
        }

    total = answered_count + len(remaining_ids)

    return {
        "event": "question_data",
        "session_id": str(session.session_id),
        "id": str(next_q.id),
        "text": next_q.text,
        "options": next_q.options,
        "category": next_q.category,
        "points": next_q.points,
        "progress": {
            "answered_count": answered_count,
            "total_questions": total,
            "remaining_count": len(remaining_ids),
        },
        # Surfaced so the frontend can show a "your level" indicator if it
        # wants; not load-bearing for the test itself.
        "skill_estimate": round(user_skill, 3),
    }


@router.post("/sessions/{session_id}/answers")
def submit_answer(
    session_id: uuid.UUID,
    payload: AnswerCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Submit an answer for a question that belongs to the session's practice.

    Side effects beyond the legacy `submit_answer`:
      - per-user `UserSkill.skill_estimate` is updated (logistic-Elo) so
        the next `get_next_question` picks a harder/easier question;
      - an answer submitted faster than `SUSPICIOUS_TIMING_SECONDS` is
        auto-logged as a `suspicious_timing` SessionEvent with
        `severity="warn"`. It counts toward the strike limit just like a
        client-reported violation.

    Same business rules as the old WS action:
      - reject if the session is already finished;
      - reject if the timer has expired (and auto-finish);
      - reject if the question isn't part of the practice;
      - reject duplicate answers for the same question;
      - score = (question.points / sum(practice question points)) * 100;
      - recalculate the question's difficulty via `calculate_difficulty_score`.

    Auto-finishes the session when this answer is the last one, or when
    the strike limit is reached.
    """
    session = _session_owned_or_404(db, session_id, current_user.id)
    if session.is_finished:
        raise HTTPException(status_code=409, detail="Session is already finished.")

    practice = session.practice or _practice_or_404(db, session.practice_id)
    if _deadline_exceeded(session, practice):
        _finish_session(db, session)
        raise HTTPException(status_code=409, detail="Test duration has expired.")

    if not practice.question_ids or payload.question_id not in practice.question_ids:
        raise HTTPException(status_code=400, detail="Question is not part of this practice.")

    existing = (
        db.query(UserAnswer.id)
        .filter(
            UserAnswer.session_id == session.session_id,
            UserAnswer.question_id == payload.question_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Question already answered.")

    question = (
        db.query(Question).filter(Question.id == payload.question_id).first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found.")

    total_weight = _total_weight_for(db, practice)
    is_correct = str(question.correct_answer) == payload.user_answer
    points_awarded = (
        (float(question.points) / total_weight) * 100 if is_correct else 0.0
    )

    answer = UserAnswer(
        id=uuid.uuid4(),
        session_id=session.session_id,
        question_id=question.id,
        user_answer=payload.user_answer,
        is_correct=is_correct,
        points_awarded=points_awarded,
        time_spent=payload.time_spent,
    )
    db.add(answer)
    db.flush()

    session.overall_points = float(session.overall_points or 0.0) + points_awarded

    # AI difficulty recalibration — same logic as the legacy WS path.
    stats = (
        db.query(
            func.count(UserAnswer.id).label("total"),
            func.sum(func.cast(UserAnswer.is_correct == False, Integer)).label("failures"),
            func.avg(UserAnswer.time_spent).label("avg_time"),
        )
        .filter(UserAnswer.question_id == question.id)
        .first()
    )
    if stats and stats.total and stats.total > 0:
        f_rate = (stats.failures or 0) / stats.total
        t_factor = float(stats.avg_time or 0)
        question.difficulty_level = calculate_difficulty_score(f_rate, t_factor)

    # Bump the user's running skill estimate so the next question
    # selection adapts.
    new_skill = _update_user_skill(
        db, current_user.id, question.difficulty_level, is_correct
    )

    # Suspicious-timing heuristic: any answer that comes in under
    # ~500ms is logged + counted as a warn-severity strike.
    suspicious = (
        payload.time_spent is not None
        and payload.time_spent < SUSPICIOUS_TIMING_SECONDS
    )
    auto_finish_for_cheating = False
    if suspicious:
        meta = _get_or_create_meta(db, session)
        db.add(
            SessionEvent(
                session_id=session.session_id,
                event_type="suspicious_timing",
                severity="warn",
                payload={
                    "time_spent": payload.time_spent,
                    "question_id": str(question.id),
                    "threshold": SUSPICIOUS_TIMING_SECONDS,
                },
            )
        )
        meta.strikes = int(meta.strikes or 0) + 1
        if meta.strikes >= STRIKE_LIMIT:
            meta.auto_finished_reason = "cheating_detected"
            auto_finish_for_cheating = True

    db.commit()
    db.refresh(session)

    answered_count = (
        db.query(func.count(UserAnswer.id))
        .filter(UserAnswer.session_id == session.session_id)
        .scalar()
    ) or 0

    total_questions = (
        len(practice.question_ids) if practice.question_ids else 0
    )
    is_finished_flag = False
    final_score: Optional[float] = None
    finish_reason: Optional[str] = None
    if auto_finish_for_cheating:
        finished = _finish_session(db, session, reason="cheating_detected", final_score=0.0)
        is_finished_flag = True
        final_score = round(float(finished.overall_points or 0.0), 2)
        finish_reason = "cheating_detected"
    elif total_questions and answered_count >= total_questions:
        finished = _finish_session(db, session)
        is_finished_flag = True
        final_score = round(float(finished.overall_points or 0.0), 2)
        finish_reason = "all_answered"

    # Latency win: we already touched everything we need (session,
    # practice, fresh user_skill, fresh answered set) to pick the next
    # question. Folding that selection into this response saves the
    # client one full HTTP round-trip per question. Selection still
    # uses the just-updated `new_skill`, so adaptivity is preserved.
    next_question_payload: Optional[dict] = None
    if not is_finished_flag and not _deadline_exceeded(session, practice):
        next_q, remaining_ids, next_answered_count = _pick_adaptive_question(
            db, session, practice, new_skill
        )
        if next_q is None:
            # All questions answered (shouldn't normally happen since we
            # finished above, but handle defensively for legacy sessions
            # with stale meta).
            finished = _finish_session(db, session)
            is_finished_flag = True
            final_score = round(float(finished.overall_points or 0.0), 2)
            finish_reason = "all_answered"
        else:
            total_for_next = next_answered_count + len(remaining_ids)
            next_question_payload = {
                "event": "question_data",
                "session_id": str(session.session_id),
                "id": str(next_q.id),
                "text": next_q.text,
                "options": next_q.options,
                "category": next_q.category,
                "points": next_q.points,
                "progress": {
                    "answered_count": next_answered_count,
                    "total_questions": total_for_next,
                    "remaining_count": len(remaining_ids),
                },
                "skill_estimate": round(new_skill, 3),
            }

    return {
        "event": "answer_result",
        "is_correct": is_correct,
        "correct_answer": str(question.correct_answer),
        "points_awarded": round(float(points_awarded), 2),
        "new_difficulty": question.difficulty_level,
        "answered_count": int(answered_count),
        "total_questions": total_questions,
        "is_finished": is_finished_flag,
        "final_score": final_score,
        "finish_reason": finish_reason,
        "skill_estimate": round(new_skill, 3),
        "suspicious_timing": bool(suspicious),
        # `null` when the test just finished; otherwise contains the
        # same shape as GET /sessions/{id}/next-question so the client
        # can render it directly without a second request.
        "next_question": next_question_payload,
    }


@router.get("/sessions/{session_id}/answers")
def list_session_answers(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns every answer the user has submitted in this session, with the
    question text and correct option id so the frontend can render a review
    screen.
    """
    session = _session_owned_or_404(db, session_id, current_user.id)
    items = _format_answers(db, session)
    return {"items": items, "total": len(items)}


@router.post("/sessions/{session_id}/abandon")
def abandon_session_endpoint(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Mark a session as finished because the student left the test page
    (tab close, navigate away, lost focus, network drop).

    The student gets graded on whatever they already answered and loses
    their chance for this practice. Admins can re-issue a new assignment
    to grant another attempt.

    This endpoint is designed to be called via `navigator.sendBeacon`
    from the frontend `visibilitychange`/`beforeunload` handlers, so it
    is intentionally fast: no anti-cheat event row is written, only the
    session is finalized with reason="abandoned".

    Idempotent — a second call on the same session is a no-op.
    """
    session = _session_owned_or_404(db, session_id, current_user.id)
    already = session.is_finished
    finished = _finish_session(db, session, reason="abandoned")
    return {
        "event": "test_finished",
        "session_id": str(finished.session_id),
        "final_score": round(float(finished.overall_points or 0.0), 2),
        "is_finished": True,
        "reason": "abandoned",
        "already_finished": already,
        "message": (
            "Session was already closed."
            if already
            else "Session marked abandoned. You can no longer continue this test."
        ),
    }


@router.post("/sessions/{session_id}/finish")
def finish_session_endpoint(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually finalize the session. Idempotent — calling on an already
    finished session just returns the final state.
    """
    session = _session_owned_or_404(db, session_id, current_user.id)
    practice = session.practice or _practice_or_404(db, session.practice_id)
    finished = _finish_session(db, session)

    answered_count = (
        db.query(func.count(UserAnswer.id))
        .filter(UserAnswer.session_id == session.session_id)
        .scalar()
    ) or 0
    total_questions = (
        len(practice.question_ids) if practice.question_ids else 0
    )

    return {
        "event": "test_finished",
        "session_id": str(finished.session_id),
        "final_score": round(float(finished.overall_points or 0.0), 2),
        "is_finished": finished.is_finished,
        "answered_count": int(answered_count),
        "total_questions": total_questions,
        "message": "Assignment completed and locked.",
    }


@router.get("/sessions/{session_id}/result")
def get_session_result(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Full per-session result: progress snapshot + every answer with its
    correctness and the correct option id.
    """
    session = _session_owned_or_404(db, session_id, current_user.id)
    progress = _session_progress(db, session)
    items = _format_answers(db, session)
    return {**progress, "answers": items}


# ==========================================
# 3. ANTI-CHEAT EVENT INGESTION + REVIEW
# ==========================================

@router.post("/sessions/{session_id}/events", status_code=status.HTTP_201_CREATED)
def report_session_event(
    session_id: uuid.UUID,
    payload: SessionEventCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Ingests an anti-cheat event from the test page (tab_blur,
    paste_attempt, devtools_open, fullscreen_exit, copy_attempt,
    right_click, screenshot_attempt, ...).

    Strike policy (configurable via `STRIKE_LIMIT`, default 3):
      - `severity=info`     — logged, no strike
      - `severity=warn` / `critical`
          * 1st & 2nd strikes → response includes
            `warning=true, strikes=N, strike_limit=STRIKE_LIMIT` and a
            human `message` like "Warning N of 3 — ..." so the client
            can show an escalating banner.
          * On the `STRIKE_LIMIT`-th strike → response includes
            `finished=true, reason="cheating_detected"`, and the
            session is auto-finalized with `assignment.is_completed=True`.

    Returns 409 if the session is already finished — clients should stop
    sending events at that point.
    """
    session = _session_owned_or_404(db, session_id, current_user.id)
    if session.is_finished:
        raise HTTPException(status_code=409, detail="Session is already finished.")

    practice = session.practice or _practice_or_404(db, session.practice_id)
    # If the timer already ran out, auto-finish before recording so the
    # client can stop polling. Don't record the event after expiry.
    if _deadline_exceeded(session, practice):
        finished = _finish_session(db, session)
        return {
            "event": "test_finished",
            "session_id": str(finished.session_id),
            "final_score": round(float(finished.overall_points or 0.0), 2),
            "reason": "duration_exceeded",
            "warning": False,
            "strikes": None,
            "finished": True,
        }

    meta = _get_or_create_meta(db, session)
    event_row = SessionEvent(
        session_id=session.session_id,
        event_type=payload.event_type[:64],
        severity=payload.severity,
        payload=payload.payload,
    )
    db.add(event_row)

    immediate_zero = payload.event_type in IMMEDIATE_ZERO_SCORE_EVENTS
    counts_as_strike = immediate_zero or payload.severity in ("warn", "critical")
    if counts_as_strike or immediate_zero:
        meta.strikes = int(meta.strikes or 0) + 1

    auto_finish = immediate_zero or (counts_as_strike and meta.strikes >= STRIKE_LIMIT)
    if auto_finish:
        meta.auto_finished_reason = "cheating_detected"

    if auto_finish:
        meta.strikes = max(int(meta.strikes or 0), STRIKE_LIMIT)
        finished = _finish_session(
            db,
            session,
            reason="cheating_detected",
            final_score=0.0,
        )
        db.refresh(event_row)
    else:
        db.commit()
        db.refresh(event_row)

    response = {
        "event": "event_recorded",
        "session_id": str(session.session_id),
        "event_id": str(event_row.id),
        "event_type": event_row.event_type,
        "severity": event_row.severity,
        "strikes": int(meta.strikes or 0),
        "strike_limit": STRIKE_LIMIT,
        "counts_as_strike": counts_as_strike,
        "warning": counts_as_strike and not auto_finish,
        "finished": False,
        "reason": None,
    }
    if auto_finish:
        response.update(
            finished=True,
            reason="cheating_detected",
            final_score=round(float(finished.overall_points or 0.0), 2),
            message=(
                "Hard integrity violation detected. The session has been "
                "closed with a zero score."
            ),
        )
    elif counts_as_strike:
        remaining = max(0, STRIKE_LIMIT - int(meta.strikes or 0))
        if remaining <= 1:
            tail = "one more violation will auto-submit your test."
        else:
            tail = f"{remaining} more violations before your test is auto-submitted."
        response["message"] = (
            f"Warning {meta.strikes} of {STRIKE_LIMIT} \u2014 {tail}"
        )
    return response


@router.get("/sessions/{session_id}/events")
def list_session_events(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns this session's anti-cheat event log (visible to the
    session owner; admins read via `/admin/test-sessions/{id}/events`).
    """
    session = _session_owned_or_404(db, session_id, current_user.id)
    rows = (
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
            "id": str(r.id),
            "event_type": r.event_type,
            "severity": r.severity,
            "payload": r.payload,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    return {
        "session_id": str(session.session_id),
        "items": items,
        "total": len(items),
        "strikes": int(meta.strikes) if meta and meta.strikes is not None else 0,
        "strike_limit": STRIKE_LIMIT,
        "auto_finished_reason": meta.auto_finished_reason if meta else None,
    }
