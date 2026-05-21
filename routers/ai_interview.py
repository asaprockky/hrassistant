"""Text-chat AI interview endpoints powered by OpenAI.

Endpoints (all under /candidate/portal/ai-interview):

  POST   /sessions                       Start a new interview (returns
                                          the opening question).
  GET    /sessions                       List the current user's interviews.
  GET    /sessions/{id}                  Read one interview with its
                                          messages and final feedback.
  POST   /sessions/{id}/messages         Send a student answer; returns
                                          the next interviewer turn.
  POST   /sessions/{id}/finish           Ask GPT to grade the conversation
                                          and store the result.
  GET    /health                         Whether OPENAI_API_KEY is set.

The OPENAI_API_KEY env var drives whether AI is available. If it is
missing every mutating endpoint returns 503 ai_unavailable so the
frontend can render a graceful empty state.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import (
    AIInterviewMessage,
    AIInterviewSession,
    User,
)
from routers.login import get_current_user
from utils.ai import (
    DEFAULT_INTERVIEW_MODEL,
    AIServiceUnavailable,
    chat_completion,
    is_configured,
    parse_json_response,
)


router = APIRouter(
    prefix="/candidate/portal/ai-interview",
    tags=["Candidate Portal"],
)


# ============================================================
# Schemas
# ============================================================

class StartInterviewRequest(BaseModel):
    role: str = Field(min_length=2, max_length=120)
    context: Optional[str] = Field(default=None, max_length=4000)


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


def _message_dict(m: AIInterviewMessage) -> dict:
    return {
        "id": str(m.id),
        "role": m.role,
        "content": m.content,
        "created_at": m.created_at,
    }


def _session_payload(s: AIInterviewSession, *, include_messages: bool = True) -> dict:
    # System messages are kept in the DB for context but should not be
    # shown to the student in the chat transcript.
    visible = [m for m in (s.messages or []) if m.role != "system"]
    payload: dict = {
        "id": str(s.id),
        "role": s.role,
        "context": s.context,
        "status": s.status,
        "created_at": s.created_at,
        "finished_at": s.finished_at,
        "final_score": s.final_score,
        "final_feedback": s.final_feedback,
        "message_count": len(visible),
    }
    if include_messages:
        payload["messages"] = [_message_dict(m) for m in visible]
    return payload


def _session_or_404(
    db: Session, session_id: uuid.UUID, user_id: uuid.UUID
) -> AIInterviewSession:
    row = (
        db.query(AIInterviewSession)
        .filter(AIInterviewSession.id == session_id)
        .first()
    )
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Interview not found")
    return row


# ============================================================
# Prompts
# ============================================================

INTERVIEWER_SYSTEM_PROMPT = (
    "You are a friendly but rigorous technical interviewer for the role of "
    "{role}. Conduct a text-only interview in English. "
    "Ground rules: ask ONE question at a time. Start with a soft warm-up, "
    "then progressively harder questions on fundamentals, hands-on "
    "scenarios, and one open-ended design / behavioural prompt. "
    "Do NOT reveal answers, do NOT teach during the interview, do NOT use "
    "more than ~120 words per turn. If the candidate's answer is shallow, "
    "ask a focused follow-up before moving on. After 6-8 substantive "
    "questions you may wrap up by saying you have enough to finalize. "
    "Never mention that you are an AI. Always stay on topic for the role."
)

GRADER_SYSTEM_PROMPT = (
    "You are an interview grader. Read the transcript and produce a strict "
    "JSON evaluation. Be honest and concise. Schema:\n"
    "{\n"
    '  "score": 0-100 integer,\n'
    '  "summary": "2-3 sentence summary",\n'
    '  "strengths": ["short bullet", ...],\n'
    '  "improvements": ["short bullet", ...],\n'
    '  "skill_breakdown": [\n'
    '    {"skill": "name", "score": 0-10, "comment": "short"}\n'
    "  ]\n"
    "}\n"
    "Return only the JSON object."
)


def _build_messages_for_followup(session: AIInterviewSession) -> list[dict]:
    # OpenAI takes the system message + the visible chat history.
    out = [{"role": "system", "content": session.messages[0].content}] if session.messages and session.messages[0].role == "system" else []
    if not out:
        out = [{"role": "system", "content": INTERVIEWER_SYSTEM_PROMPT.format(role=session.role)}]
    for m in session.messages or []:
        if m.role == "system":
            continue
        out.append({"role": m.role, "content": m.content})
    return out


# ============================================================
# Routes
# ============================================================

@router.get("/health")
def ai_interview_health() -> dict:
    """Whether the OpenAI integration is configured. Safe to call
    without authentication-style side effects so the UI can decide
    whether to show the AI interview page or a 'coming soon' card.
    """
    return {
        "configured": is_configured(),
        "model": DEFAULT_INTERVIEW_MODEL,
    }


@router.get("/sessions")
def list_interviews(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = (
        db.query(AIInterviewSession)
        .filter(AIInterviewSession.user_id == current_user.id)
        .order_by(AIInterviewSession.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "items": [_session_payload(r, include_messages=False) for r in rows],
        "configured": is_configured(),
    }


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def start_interview(
    body: StartInterviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    role = body.role.strip()[:120]
    context = (body.context or "").strip() or None

    # Build the persisted system prompt (with the role baked in) so
    # subsequent turns can rebuild the OpenAI request without
    # re-deriving it.
    system_prompt = INTERVIEWER_SYSTEM_PROMPT.format(role=role)
    if context:
        system_prompt += (
            "\n\nAdditional context from the candidate:\n"
            + context[:4000]
        )

    # Ask GPT for the opening question before persisting anything, so
    # that if OpenAI is broken we don't leave an empty session lying
    # around.
    opening_messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "Please begin the interview now. Start with a short, friendly "
                "introduction (one sentence), then ask your first question."
            ),
        },
    ]
    opening = chat_completion(
        opening_messages,
        temperature=0.6,
        max_tokens=300,
    )

    session = AIInterviewSession(
        id=uuid.uuid4(),
        user_id=current_user.id,
        role=role,
        context=context,
        status="active",
        created_at=datetime.utcnow(),
    )
    db.add(session)
    db.flush()
    db.add(
        AIInterviewMessage(
            id=uuid.uuid4(),
            session_id=session.id,
            role="system",
            content=system_prompt,
            created_at=datetime.utcnow(),
        )
    )
    db.add(
        AIInterviewMessage(
            id=uuid.uuid4(),
            session_id=session.id,
            role="assistant",
            content=opening.strip(),
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    db.refresh(session)
    return _session_payload(session)


@router.get("/sessions/{session_id}")
def get_interview(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    session = _session_or_404(db, session_id, current_user.id)
    return _session_payload(session)


@router.post("/sessions/{session_id}/messages", status_code=status.HTTP_201_CREATED)
def send_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    session = _session_or_404(db, session_id, current_user.id)
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Interview is already finished")

    student_msg = AIInterviewMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="user",
        content=body.content.strip()[:4000],
        created_at=datetime.utcnow(),
    )
    db.add(student_msg)
    db.flush()
    # Re-read to include the new student message in the OpenAI request.
    db.refresh(session)

    next_turn = chat_completion(
        _build_messages_for_followup(session),
        temperature=0.5,
        max_tokens=300,
    )
    interviewer_msg = AIInterviewMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="assistant",
        content=next_turn.strip(),
        created_at=datetime.utcnow(),
    )
    db.add(interviewer_msg)
    db.commit()
    db.refresh(session)
    return {
        "student_message": _message_dict(student_msg),
        "interviewer_message": _message_dict(interviewer_msg),
        "session": _session_payload(session, include_messages=False),
    }


@router.post("/sessions/{session_id}/finish")
def finish_interview(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    session = _session_or_404(db, session_id, current_user.id)
    if session.status == "finished":
        return _session_payload(session)

    transcript_lines: list[str] = []
    for m in session.messages or []:
        if m.role == "system":
            continue
        speaker = "Interviewer" if m.role == "assistant" else "Candidate"
        transcript_lines.append(f"{speaker}: {m.content}")
    transcript = "\n".join(transcript_lines).strip() or "(no answers)"

    grading = chat_completion(
        [
            {"role": "system", "content": GRADER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Role being interviewed for: {session.role}\n\n"
                    f"Transcript:\n{transcript}\n\n"
                    "Return only the JSON evaluation."
                ),
            },
        ],
        temperature=0.2,
        max_tokens=600,
        response_format={"type": "json_object"},
    )
    try:
        parsed = parse_json_response(grading)
    except AIServiceUnavailable:
        # If GPT didn't return JSON, fall back to a "needs review"
        # payload so the row is still closed and the student isn't
        # locked out.
        parsed = {
            "score": None,
            "summary": "AI could not finalize a grade. Please review the transcript manually.",
            "strengths": [],
            "improvements": [],
            "skill_breakdown": [],
        }

    score = parsed.get("score")
    try:
        final_score = float(score) if score is not None else None
    except (TypeError, ValueError):
        final_score = None

    session.status = "finished"
    session.finished_at = datetime.utcnow()
    session.final_score = final_score
    session.final_feedback = parsed
    db.commit()
    db.refresh(session)
    return _session_payload(session)
