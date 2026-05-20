import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Integer, and_, func
from sqlalchemy.orm import Session, joinedload

from database.database import get_db
from database.models import (
    Practice,
    PracticeAssignment,
    Question,
    TestSession,
    UserAnswer,
)
from routers.login import get_current_user
from schemas.user_schema import AnswerCreate
from utils.ai_logic import calculate_difficulty_score


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


def _finish_session(db: Session, session: TestSession) -> TestSession:
    """Idempotent finalize: marks the session finished and the matching
    PracticeAssignment completed. Safe to call multiple times.
    """
    if session.is_finished:
        return session

    session.is_finished = True

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
    """Returns whether the current user can start, must resume, or has already
    completed the practice — so the frontend can render the right CTA without
    making a POST and parsing a 4xx.

    Response `status` values:
      - `not_found`            — practice doesn't exist or is invalidated
      - `not_invited`          — user has no PracticeAssignment for this practice
      - `assignment_completed` — assignment is marked completed (no session yet,
                                 e.g. set by an admin)
      - `deadline_passed`      — practice deadline is in the past
      - `finished`             — a finished TestSession already exists
      - `duration_exceeded`    — an in-progress session's timer has expired;
                                 calling `start` is still blocked
      - `in_progress`          — user has an active session to resume
      - `eligible`             — user can call POST /sessions to start
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
                "reason": "You have already completed this test.",
            }
        if _deadline_exceeded(existing, practice):
            return {
                "status": "duration_exceeded",
                "can_start": False,
                "can_resume": False,
                "session_id": str(existing.session_id),
                "reason": "Test duration has expired.",
            }
        return {
            "status": "in_progress",
            "can_start": False,
            "can_resume": True,
            "session_id": str(existing.session_id),
            "reason": None,
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
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Creates a new TestSession for the current user against a practice.

    Mirrors the old `start_test` WebSocket action: same invitation /
    completion / re-entry / deadline checks. Returns 409 with the existing
    session id when a session already exists so clients can resume.
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
        raise HTTPException(
            status_code=409,
            detail={
                "message": "A session already exists for this practice. Re-entry is not allowed.",
                "session_id": str(existing.session_id),
                "is_finished": existing.is_finished,
            },
        )

    now = _utcnow()
    if practice.deadline and practice.deadline < now:
        raise HTTPException(status_code=409, detail="Practice deadline has passed.")

    session = TestSession(
        session_id=uuid.uuid4(),
        practice_id=practice_id,
        user_id=current_user.id,
        overall_points=0.0,
        is_finished=False,
        started_time=now,
    )
    db.add(session)
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
    """Returns the next unanswered question for the session, in
    `Practice.question_ids` order. Auto-finishes the session when all
    questions are answered or the timer has expired.

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

    answered_ids = {
        row[0]
        for row in db.query(UserAnswer.question_id)
        .filter(UserAnswer.session_id == session.session_id)
        .all()
    }
    remaining_ids = [
        q for q in (practice.question_ids or []) if q not in answered_ids
    ]

    if not remaining_ids:
        finished = _finish_session(db, session)
        return {
            "event": "test_finished",
            "session_id": str(finished.session_id),
            "final_score": round(float(finished.overall_points or 0.0), 2),
            "reason": "all_answered",
        }

    qs_by_id = {
        q.id: q
        for q in db.query(Question).filter(Question.id.in_(remaining_ids)).all()
    }
    next_q = None
    for q_id in remaining_ids:
        candidate = qs_by_id.get(q_id)
        if candidate:
            next_q = candidate
            break

    if not next_q:
        finished = _finish_session(db, session)
        return {
            "event": "test_finished",
            "session_id": str(finished.session_id),
            "final_score": round(float(finished.overall_points or 0.0), 2),
            "reason": "all_answered",
        }

    total = len(practice.question_ids) if practice.question_ids else 0
    answered_count = total - len(remaining_ids)

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
    }


@router.post("/sessions/{session_id}/answers")
def submit_answer(
    session_id: uuid.UUID,
    payload: AnswerCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Submit an answer for a question that belongs to the session's practice.

    Same business rules as the old `submit_answer` WS action:
      - reject if the session is already finished;
      - reject if the timer has expired (and auto-finish);
      - reject if the question isn't part of the practice;
      - reject duplicate answers for the same question;
      - score = (question.points / sum(practice question points)) * 100;
      - recalculate the question's difficulty via `calculate_difficulty_score`.

    Auto-finishes the session when this answer is the last one.
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
    if total_questions and answered_count >= total_questions:
        finished = _finish_session(db, session)
        is_finished_flag = True
        final_score = round(float(finished.overall_points or 0.0), 2)

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
