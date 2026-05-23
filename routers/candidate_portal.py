import math
import os
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, EmailStr, Field
from PyPDF2 import PdfReader
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from database.database import get_db
from database.models import (
    Candidate,
    CandidateCertificate,
    CandidateNotificationState,
    CandidateProfile,
    CandidateResumeReview,
    Created_Vacancy,
    Practice,
    PracticeAssignment,
    Question,
    TestSession,
    User,
    UserAnswer,
)
from routers.login import get_current_user


router = APIRouter(prefix="/candidate/portal", tags=["Candidate Portal"])


UPLOAD_ROOT = Path("uploads") / "resumes"
AVATAR_ROOT = Path("uploads") / "avatars"
MAX_RESUME_BYTES = 5 * 1024 * 1024
MAX_AVATAR_BYTES = 3 * 1024 * 1024


class CandidateProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=30)
    surname: Optional[str] = Field(None, min_length=1, max_length=30)
    email: Optional[EmailStr] = None
    headline: Optional[str] = Field(None, max_length=150)
    location: Optional[str] = Field(None, max_length=100)
    university: Optional[str] = Field(None, max_length=150)
    graduation_year: Optional[str] = Field(None, max_length=10)
    phone: Optional[str] = Field(None, max_length=30)
    portfolio_url: Optional[str] = Field(None, max_length=255)
    linkedin_url: Optional[str] = Field(None, max_length=255)
    open_to_work: Optional[bool] = None


class CertificateCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    provider: Optional[str] = Field(None, max_length=150)
    issued_at: Optional[date] = None
    tags: list[str] = Field(default_factory=list)
    credential_id: Optional[str] = Field(None, max_length=80)
    external_url: Optional[str] = Field(None, max_length=255)
    file_url: Optional[str] = Field(None, max_length=255)
    verification_notes: Optional[str] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _full_name(user: User) -> str:
    return f"{user.name} {user.surname}".strip() or user.username


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _percent(value: float) -> int:
    return max(0, min(100, int(round(value or 0))))


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


def _format_duration(seconds: Optional[float]) -> str:
    total = _safe_int(seconds)
    if total <= 0:
        return "0m"
    minutes, secs = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"
    if secs:
        return f"{minutes}m {secs}s"
    return f"{minutes}m"


def _ensure_profile(db: Session, user: User) -> CandidateProfile:
    profile = (
        db.query(CandidateProfile)
        .filter(CandidateProfile.user_id == user.id)
        .first()
    )
    if profile:
        return profile

    profile = CandidateProfile(
        id=uuid.uuid4(),
        user_id=user.id,
        headline="Candidate",
        open_to_work=True,
        updated_at=_utcnow(),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _latest_resume_review(db: Session, user_id: uuid.UUID) -> Optional[CandidateResumeReview]:
    return (
        db.query(CandidateResumeReview)
        .filter(CandidateResumeReview.user_id == user_id)
        .order_by(CandidateResumeReview.created_at.desc())
        .first()
    )


def _session_by_practice(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, TestSession]:
    sessions = (
        db.query(TestSession)
        .options(joinedload(TestSession.practice))
        .filter(TestSession.user_id == user_id)
        .order_by(TestSession.started_time.desc())
        .all()
    )
    by_practice: dict[uuid.UUID, TestSession] = {}
    for session in sessions:
        by_practice.setdefault(session.practice_id, session)
    return by_practice


def _difficulty_label(avg_difficulty: Optional[float], duration_minutes: Optional[int]) -> str:
    value = float(avg_difficulty or 0)
    if value >= 0.67 or (duration_minutes or 0) >= 75:
        return "Hard"
    if value >= 0.34 or (duration_minutes or 0) >= 40:
        return "Med"
    return "Easy"


def _question_stats(db: Session, practice: Optional[Practice]) -> dict:
    if not practice or not practice.question_ids:
        return {"count": 0, "avg_difficulty": 0.0, "categories": []}

    rows = (
        db.query(Question.category, func.avg(Question.difficulty_level), func.count(Question.id))
        .filter(Question.id.in_(practice.question_ids))
        .group_by(Question.category)
        .all()
    )
    categories = [
        {
            "name": row[0] or "General",
            "avg_difficulty": float(row[1] or 0),
            "question_count": int(row[2] or 0),
        }
        for row in rows
    ]
    total_count = sum(item["question_count"] for item in categories)
    avg = (
        sum(item["avg_difficulty"] * item["question_count"] for item in categories) / total_count
        if total_count
        else 0.0
    )
    return {"count": total_count, "avg_difficulty": avg, "categories": categories}


def _assessment_status(assignment: PracticeAssignment, session: Optional[TestSession], now: datetime) -> dict:
    practice = assignment.practice
    if session and session.is_finished:
        score = _percent(session.overall_points)
        return {
            "status": "completed",
            "status_label": "Completed",
            "status_tone": "success",
            "cta_label": "View Report",
            "cta_url": f"/candidate/portal/reports/{session.session_id}",
            "score": score,
            "progress": score,
        }
    if assignment.is_completed:
        return {
            "status": "in_review",
            "status_label": "In Review",
            "status_tone": "warning",
            "cta_label": "Awaiting Results",
            "cta_url": None,
            "score": None,
            "progress": None,
        }
    if session and not session.is_finished:
        return {
            "status": "draft",
            "status_label": "Draft",
            "status_tone": "neutral",
            "cta_label": "Continue Assessment",
            "cta_url": f"/testing/sessions/{session.session_id}",
            "score": _percent(session.overall_points),
            "progress": _percent(session.overall_points),
        }
    if practice and practice.deadline and practice.deadline < now:
        return {
            "status": "locked",
            "status_label": "Locked",
            "status_tone": "muted",
            "cta_label": "Closed",
            "cta_url": None,
            "score": None,
            "progress": None,
        }
    return {
        "status": "active",
        "status_label": "Action Required",
        "status_tone": "danger",
        "cta_label": "Start Assessment",
        "cta_url": f"/testing/practices/{assignment.practice_id}",
        "score": None,
        "progress": None,
    }


def _assessment_card(db: Session, assignment: PracticeAssignment, session: Optional[TestSession], now: datetime) -> dict:
    practice = assignment.practice
    q_stats = _question_stats(db, practice)
    status_info = _assessment_status(assignment, session, now)
    tags = practice.tags or [] if practice else []
    category = tags[0] if tags else (q_stats["categories"][0]["name"] if q_stats["categories"] else "Technical")

    return {
        "practice_id": str(assignment.practice_id),
        "assignment_id": str(assignment.assignment_id),
        "session_id": str(session.session_id) if session else None,
        "title": practice.title if practice else "Assessment",
        "description": practice.description if practice else "",
        "category": category,
        "tags": tags,
        "duration_minutes": practice.duration_minutes if practice else 0,
        "deadline": practice.deadline if practice else None,
        "assigned_at": assignment.assigned_at,
        "completed_at": assignment.completed_at,
        "question_count": q_stats["count"],
        "difficulty": _difficulty_label(q_stats["avg_difficulty"], practice.duration_minutes if practice else None),
        **status_info,
    }


def _load_assessment_cards(db: Session, user_id: uuid.UUID) -> list[dict]:
    assignments = (
        db.query(PracticeAssignment)
        .options(joinedload(PracticeAssignment.practice))
        .filter(PracticeAssignment.user_id == user_id)
        .order_by(PracticeAssignment.assigned_at.desc())
        .all()
    )
    sessions_by_practice = _session_by_practice(db, user_id)
    now = _utcnow()
    return [
        _assessment_card(db, assignment, sessions_by_practice.get(assignment.practice_id), now)
        for assignment in assignments
        if assignment.practice
    ]


def _analytics_from_sessions(db: Session, user_id: uuid.UUID) -> dict:
    sessions = (
        db.query(TestSession)
        .options(joinedload(TestSession.practice))
        .filter(TestSession.user_id == user_id)
        .order_by(TestSession.started_time.asc())
        .all()
    )
    session_ids = [session.session_id for session in sessions]
    finished = [session for session in sessions if session.is_finished]

    answers = (
        db.query(UserAnswer).filter(UserAnswer.session_id.in_(session_ids)).all()
        if session_ids
        else []
    )
    question_ids = list({answer.question_id for answer in answers if answer.question_id})
    questions_by_id = (
        {q.id: q for q in db.query(Question).filter(Question.id.in_(question_ids)).all()}
        if question_ids
        else {}
    )

    category_totals: dict[str, dict] = {}
    for answer in answers:
        question = questions_by_id.get(answer.question_id)
        category = question.category if question and question.category else "General"
        bucket = category_totals.setdefault(
            category,
            {"category": category, "earned": 0.0, "possible": 0.0, "answered": 0, "correct": 0},
        )
        bucket["earned"] += float(answer.points_awarded or 0)
        bucket["possible"] += 100.0 / max(1, len(session_ids))
        bucket["answered"] += 1
        if answer.is_correct:
            bucket["correct"] += 1

    categories = []
    for bucket in category_totals.values():
        accuracy = (bucket["correct"] / bucket["answered"]) * 100 if bucket["answered"] else 0
        categories.append(
            {
                "category": bucket["category"],
                "score": _percent(accuracy),
                "answered": bucket["answered"],
                "correct": bucket["correct"],
            }
        )
    categories.sort(key=lambda item: item["score"], reverse=True)

    average_score = (
        _percent(sum(float(session.overall_points or 0) for session in finished) / len(finished))
        if finished
        else 0
    )
    best_score = max((_percent(session.overall_points) for session in finished), default=0)
    total_time = sum(float(answer.time_spent or 0) for answer in answers)

    return {
        "overview": {
            "assigned_assessments": (
                db.query(func.count(PracticeAssignment.assignment_id))
                .filter(PracticeAssignment.user_id == user_id)
                .scalar()
                or 0
            ),
            "started_assessments": len(sessions),
            "completed_assessments": len(finished),
            "average_score": average_score,
            "best_score": best_score,
            "total_time_seconds": int(total_time),
            "total_time_label": _format_duration(total_time),
        },
        "categories": categories,
        "timeline": [
            {
                "session_id": str(session.session_id),
                "practice_id": str(session.practice_id),
                "title": session.practice.title if session.practice else "Assessment",
                "score": _percent(session.overall_points),
                "is_finished": session.is_finished,
                "started_at": session.started_time,
            }
            for session in sessions
        ],
    }


def _latest_candidate(db: Session, user_id: uuid.UUID) -> Optional[Candidate]:
    return (
        db.query(Candidate)
        .options(joinedload(Candidate.vacancy).joinedload(Created_Vacancy.company))
        .filter(Candidate.user_id == user_id)
        .order_by(Candidate.created_at.desc())
        .first()
    )


def _profile_strength(user: User, profile: CandidateProfile, analytics: dict, cert_count: int, has_review: bool) -> int:
    score = 35
    fields = [
        user.email,
        profile.headline,
        profile.location,
        profile.phone,
        profile.portfolio_url,
        profile.linkedin_url,
        profile.university,
    ]
    score += sum(5 for field in fields if field)
    if analytics["overview"]["completed_assessments"]:
        score += 10
    if cert_count:
        score += min(10, cert_count * 3)
    if has_review:
        score += 10
    return _percent(score)


def _profile_payload(db: Session, user: User) -> dict:
    profile = _ensure_profile(db, user)
    analytics = _analytics_from_sessions(db, user.id)
    latest_candidate = _latest_candidate(db, user.id)
    latest_review = _latest_resume_review(db, user.id)
    cert_count = (
        db.query(func.count(CandidateCertificate.id))
        .filter(CandidateCertificate.user_id == user.id)
        .scalar()
    ) or 0
    strength = _profile_strength(user, profile, analytics, int(cert_count), latest_review is not None)

    headline = profile.headline
    if (not headline or headline == "Candidate") and latest_candidate:
        if latest_candidate.skills:
            headline = latest_candidate.skills
        elif latest_candidate.vacancy:
            headline = latest_candidate.vacancy.job_name
        else:
            headline = "Candidate"

    categories = analytics["categories"]
    strongest = categories[0]["category"] if categories else "Core Skills"
    weakest = categories[-1]["category"] if categories else "Portfolio Depth"
    avg_score = analytics["overview"]["average_score"]

    return {
        "profile": {
            "id": str(user.id),
            "username": user.username,
            "full_name": _full_name(user),
            "name": user.name,
            "surname": user.surname,
            "role": "CANDIDATE",
            "headline": headline or "Candidate",
            "location": profile.location,
            "university": profile.university,
            "graduation_year": profile.graduation_year,
            "open_to_work": bool(profile.open_to_work),
            "avatar_url": profile.avatar_url,
            "avatar_initials": "".join(part[:1] for part in [user.name, user.surname] if part).upper() or "U",
        },
        "contact": {
            "email": user.email,
            "phone": profile.phone,
            "portfolio_url": profile.portfolio_url,
            "linkedin_url": profile.linkedin_url,
        },
        "profile_strength": {
            "score": strength,
            "label": "Top 15% of candidates in your cohort" if strength >= 80 else "Keep improving your candidate signal",
            "improve_url": "/candidate/portal/ai-profile",
        },
        "ai_review": {
            "title": "NEXUS AI Professional Review",
            "updated_at": latest_review.created_at if latest_review else profile.updated_at,
            "summary": "Deep learning analysis of your assessment performance, resume, and market fit.",
            "insights": [
                {
                    "type": "strength",
                    "title": f"High Potential in {strongest}",
                    "body": f"Your assessment data places {strongest} as your strongest area with an average score of {avg_score}%.",
                    "score": avg_score,
                },
                {
                    "type": "improvement",
                    "title": f"{weakest} Optimization Needed",
                    "body": f"Your next learning plan should include targeted practice around {weakest}.",
                    "score": categories[-1]["score"] if categories else None,
                },
                {
                    "type": "communication",
                    "title": "Communication Pattern Analysis",
                    "body": "Your profile should highlight collaborative project outcomes, measurable impact, and technical ownership.",
                    "score": strength,
                },
            ],
        },
        "linkedin_optimization": {
            "current_headline": profile.headline or "Student",
            "suggested_headline": _suggest_headline(headline, categories),
            "recommendations": [
                "Add measurable project outcomes to your headline and portfolio.",
                "Mention your strongest assessed skill in the first sentence.",
                "Attach verified certificates to improve recruiter trust.",
            ],
        },
        "career_roadmap": _career_roadmap(categories, analytics["overview"]["completed_assessments"], int(cert_count)),
    }


def _suggest_headline(headline: Optional[str], categories: list[dict]) -> str:
    strongest = categories[0]["category"] if categories else "Full Stack"
    base = headline if headline and headline != "Candidate" else strongest
    return f"Aspiring {base} Engineer | {strongest} Focus"


def _career_roadmap(categories: list[dict], completed: int, cert_count: int) -> list[dict]:
    strongest = categories[0]["category"] if categories else "Frontend Basics"
    weakest = categories[-1]["category"] if categories else "Containerization"
    return [
        {
            "title": strongest,
            "subtitle": "Validated assessment performance",
            "status": "achieved" if completed else "in_progress",
            "progress": 100 if completed else 40,
        },
        {
            "title": "Verified Credentials",
            "subtitle": "Certificates attached to profile",
            "status": "achieved" if cert_count else "missing",
            "progress": 100 if cert_count else 0,
        },
        {
            "title": weakest,
            "subtitle": "Recommended next learning focus",
            "status": "in_progress" if completed else "missing",
            "progress": 60 if completed else 0,
        },
        {
            "title": "Portfolio Polish",
            "subtitle": "Add project proof and measurable outcomes",
            "status": "goal",
            "progress": 0,
        },
    ]


def _generated_certificates(db: Session, user_id: uuid.UUID) -> list[dict]:
    sessions = (
        db.query(TestSession)
        .options(joinedload(TestSession.practice))
        .filter(
            TestSession.user_id == user_id,
            TestSession.is_finished == True,
            TestSession.overall_points >= 80,
        )
        .order_by(TestSession.started_time.desc())
        .all()
    )
    items = []
    for session in sessions:
        practice = session.practice
        score = _percent(session.overall_points)
        credential = f"ZK-{str(session.session_id)[:4].upper()}-{score}"
        items.append(
            {
                "id": f"assessment:{session.session_id}",
                "source": "assessment",
                "title": practice.title if practice else "Assessment Certificate",
                "provider": "Zukko",
                "issued_at": session.started_time.date() if session.started_time else None,
                "status": "verified",
                "badge_label": "ZUKKO VERIFIED" if score < 95 else "TOP 5%",
                "credential_id": credential,
                "tags": practice.tags or [] if practice else [],
                "score": score,
                "download_url": f"/candidate/portal/certificates/{credential}/download",
                "share_url": f"/candidate/portal/certificates/{credential}/share",
                "verification_notes": None,
            }
        )
    return items


def _external_certificate_payload(certificate: CandidateCertificate) -> dict:
    return {
        "id": str(certificate.id),
        "source": "external",
        "title": certificate.title,
        "provider": certificate.provider,
        "issued_at": certificate.issued_at,
        "status": certificate.status,
        "badge_label": certificate.badge_label or ("VERIFIED" if certificate.status == "verified" else "AUDIT PENDING"),
        "credential_id": certificate.credential_id,
        "tags": certificate.tags or [],
        "score": None,
        "download_url": certificate.file_url,
        "share_url": certificate.external_url,
        "verification_notes": certificate.verification_notes,
    }


def _certificate_items(db: Session, user_id: uuid.UUID, status_filter: str) -> list[dict]:
    external = (
        db.query(CandidateCertificate)
        .filter(CandidateCertificate.user_id == user_id)
        .order_by(CandidateCertificate.created_at.desc())
        .all()
    )
    items = [_external_certificate_payload(item) for item in external]
    items.extend(_generated_certificates(db, user_id))
    if status_filter != "all":
        items = [item for item in items if item["status"] == status_filter]
    return items


def _certificate_counts(items: list[dict]) -> dict:
    return {
        "all": len(items),
        "verified": len([item for item in items if item["status"] == "verified"]),
        "pending": len([item for item in items if item["status"] == "pending"]),
    }


def _resume_review_payload(review: Optional[CandidateResumeReview]) -> Optional[dict]:
    if not review:
        return None
    return {
        "id": str(review.id),
        "filename": review.filename,
        "file_url": review.file_url,
        "score": _percent(review.score),
        "analysis_summary": review.analysis_summary,
        "strengths": review.strengths or [],
        "suggestions": review.suggestions or [],
        "created_at": review.created_at,
    }


def _extract_resume_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
        return " ".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _heuristic_resume_review(text: str) -> dict:
    """Cheap keyword-based fallback used when no OPENAI_API_KEY is set.
    Kept around so the endpoint still produces a usable response in
    dev / offline environments.
    """
    normalized = text.lower()
    score = 55
    checks = [
        ("metrics", any(token in normalized for token in ["%", "increased", "reduced", "improved", "saved"])),
        ("projects", "project" in normalized or "portfolio" in normalized),
        ("skills", any(token in normalized for token in ["python", "react", "sql", "javascript", "aws", "docker"])),
        ("leadership", any(token in normalized for token in ["led", "managed", "owned", "collaborated"])),
        ("education", any(token in normalized for token in ["university", "degree", "bachelor", "master"])),
    ]
    score += sum(8 for _, passed in checks if passed)
    strengths = [
        "Strong action verbs used." if checks[3][1] else "Clear technical skills are present.",
        "Technical keyword coverage looks healthy." if checks[2][1] else "Resume is readable and ready for improvement.",
    ]
    suggestions = []
    if not checks[0][1]:
        suggestions.append('Add metrics to project bullets, for example "improved latency by 30%".')
    if not checks[1][1]:
        suggestions.append("Add 2-3 portfolio projects with links and clear ownership.")
    if not checks[2][1]:
        suggestions.append("Add a compact skills section matching target roles.")
    if not suggestions:
        suggestions.append("Tailor the first summary paragraph to the specific role before applying.")
    return {
        "score": _percent(score),
        "summary": "Heuristic resume analysis completed from uploaded PDF content.",
        "strengths": strengths,
        "suggestions": suggestions,
    }


_RESUME_SYSTEM_PROMPT = (
    "You are an experienced technical recruiter and resume reviewer. "
    "Read the resume text provided and produce a strict JSON evaluation. "
    "Be honest but constructive. Schema:\n"
    "{\n"
    '  "score": 0-100 integer overall resume strength,\n'
    '  "summary": "2-3 sentence overall impression",\n'
    '  "strengths": ["short bullet", ...],\n'
    '  "suggestions": ["actionable rewrite tip", ...]\n'
    "}\n"
    "Return only the JSON object."
)


def _analyze_resume(text: str) -> dict:
    """AI-powered resume review. Uses OpenAI when OPENAI_API_KEY is
    configured, otherwise falls back to the keyword heuristic so the
    endpoint never returns 503 just because AI is offline.
    """
    from utils.ai import (
        AIServiceUnavailable,
        chat_completion,
        is_configured,
        parse_json_response,
    )

    if not is_configured():
        return _heuristic_resume_review(text)

    truncated = (text or "").strip()
    if not truncated:
        return _heuristic_resume_review(text)
    # OpenAI input cap; keep the prompt cheap.
    truncated = truncated[:8000]

    try:
        raw = chat_completion(
            [
                {"role": "system", "content": _RESUME_SYSTEM_PROMPT},
                {"role": "user", "content": f"Resume text:\n{truncated}"},
            ],
            temperature=0.2,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        parsed = parse_json_response(raw)
    except AIServiceUnavailable:
        return _heuristic_resume_review(text)

    score = parsed.get("score")
    try:
        score_int = int(round(float(score)))
    except (TypeError, ValueError):
        score_int = 50
    return {
        "score": _percent(score_int),
        "summary": (parsed.get("summary") or "AI resume review completed.")[:1000],
        "strengths": [str(s)[:200] for s in (parsed.get("strengths") or [])][:6],
        "suggestions": [str(s)[:200] for s in (parsed.get("suggestions") or [])][:6],
    }


def _notifications_from_cards(db: Session, user_id: uuid.UUID, cards: Optional[list[dict]] = None) -> list[dict]:
    cards = cards if cards is not None else _load_assessment_cards(db, user_id)
    now = _utcnow()
    items = []
    state = (
        db.query(CandidateNotificationState)
        .filter(CandidateNotificationState.user_id == user_id)
        .first()
    )
    last_read_at = state.last_read_at if state else None

    def enrich(item: dict) -> dict:
        created_at = item.get("created_at") or now
        item["id"] = item.get("id") or f"{item['type']}:{item['title']}:{created_at.isoformat() if hasattr(created_at, 'isoformat') else created_at}"
        item["created_at"] = created_at
        item["is_read"] = bool(last_read_at and created_at and created_at <= last_read_at)
        return item

    for card in cards:
        if card["status"] not in {"active", "draft"}:
            continue
        deadline = card.get("deadline")
        due_soon = bool(deadline and (deadline - now).days <= 7)
        items.append(enrich(
            {
                "id": f"assessment:{card['assignment_id']}",
                "type": "assessment",
                "title": card["title"],
                "message": "Due soon" if due_soon else card["status_label"],
                "priority": "high" if due_soon and card["status"] == "active" else "normal",
                "created_at": card.get("assigned_at"),
                "action_label": card["cta_label"],
                "action_url": card["cta_url"],
            }
        ))

    pending_certs_row = (
        db.query(func.count(CandidateCertificate.id), func.min(CandidateCertificate.created_at))
        .filter(
            CandidateCertificate.user_id == user_id,
            CandidateCertificate.status == "pending",
        )
        .first()
    )
    pending_certs = int(pending_certs_row[0] or 0) if pending_certs_row else 0
    if pending_certs:
        items.append(enrich(
            {
                "id": "certificate:pending",
                "type": "certificate",
                "title": "Certificate verification",
                "message": f"{pending_certs} certificate{'s' if pending_certs != 1 else ''} pending audit.",
                "priority": "normal",
                "created_at": pending_certs_row[1] or now,
                "action_label": "View Vault",
                "action_url": "/candidate/portal/certificates",
            }
        ))

    latest_review = _latest_resume_review(db, user_id)
    if latest_review:
        items.append(enrich(
            {
                "id": f"resume_review:{latest_review.id}",
                "type": "resume_review",
                "title": "Resume review ready",
                "message": f"Latest score: {_percent(latest_review.score)}/100.",
                "priority": "normal",
                "created_at": latest_review.created_at,
                "action_label": "View Review",
                "action_url": "/candidate/portal/resume-reviews/latest",
            }
        ))

    return items[:10]


def _find_certificate_item(db: Session, user_id: uuid.UUID, certificate_key: str) -> dict:
    for item in _certificate_items(db, user_id, "all"):
        if item["id"] == certificate_key or item.get("credential_id") == certificate_key:
            return item
    raise HTTPException(status_code=404, detail="Certificate not found")


@router.get("/me")
def get_candidate_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "full_name": _full_name(current_user),
        "name": current_user.name,
        "surname": current_user.surname,
        "email": current_user.email,
        "role": current_user.role,
        "group_name": current_user.group_name,
        "avatar_url": current_user.candidate_profile.avatar_url if current_user.candidate_profile else None,
        "student_id": f"#{str(current_user.id)[:6].upper()}",
        "avatar_initials": "".join(part[:1] for part in [current_user.name, current_user.surname] if part).upper() or "U",
    }


@router.get("/dashboard")
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cards = _load_assessment_cards(db, current_user.id)
    active = [card for card in cards if card["status"] in {"active", "draft"}]
    completed = [card for card in cards if card["status"] == "completed"]
    latest_review = _latest_resume_review(db, current_user.id)
    certs = _certificate_items(db, current_user.id, "all")
    notifications = _notifications_from_cards(db, current_user.id, cards)
    unread_notifications = len([item for item in notifications if not item.get("is_read")])

    return {
        "greeting": {
            "headline": f"Good morning, {current_user.name}",
            "message": f"You have {len(active)} active assessments pending and {1 if latest_review else 0} resume review available.",
        },
        "stats": {
            "active_assessments": len(active),
            "completed_assessments": len(completed),
            "average_score": _percent(sum(card["score"] or 0 for card in completed) / len(completed)) if completed else 0,
            "certificates": len(certs),
            "notifications": unread_notifications,
        },
        "active_assessments": active[:2],
        "recent_activity": [
            {
                "title": card["title"],
                "date": card["completed_at"] or card["assigned_at"],
                "status": card["status_label"],
                "score": card["score"],
                "action_url": card["cta_url"],
            }
            for card in (completed[:5] or cards[:5])
        ],
        "resume_insights": _resume_review_payload(latest_review),
        "certificates_preview": certs[:6],
        "notifications_preview": notifications[:5],
        "profile_share_url": "/candidate/portal/profile/share",
    }


@router.get("/assessments")
def list_assessments(
    status_filter: str = Query("all", alias="status"),
    search: Optional[str] = None,
    difficulty: Optional[str] = None,
    sort: str = Query("newest"),
    page: int = Query(1, ge=1),
    size: int = Query(6, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = _load_assessment_cards(db, current_user.id)
    counts = {
        "all": len(items),
        "active": len([item for item in items if item["status"] in {"active", "draft"}]),
        "completed": len([item for item in items if item["status"] == "completed"]),
        "drafts": len([item for item in items if item["status"] == "draft"]),
        "locked": len([item for item in items if item["status"] == "locked"]),
    }

    if status_filter != "all":
        aliases = {"drafts": "draft", "pending": "active"}
        expected = aliases.get(status_filter, status_filter)
        if expected == "active":
            items = [item for item in items if item["status"] in {"active", "draft"}]
        else:
            items = [item for item in items if item["status"] == expected]
    if search:
        pattern = search.lower()
        items = [
            item for item in items
            if pattern in item["title"].lower() or pattern in (item["description"] or "").lower()
        ]
    if difficulty and difficulty.lower() != "all":
        items = [item for item in items if item["difficulty"].lower() == difficulty.lower()]

    if sort == "oldest":
        items.sort(key=lambda item: item["assigned_at"] or datetime.min)
    elif sort == "deadline":
        items.sort(key=lambda item: item["deadline"] or datetime.max)
    elif sort == "score":
        items.sort(key=lambda item: item["score"] or -1, reverse=True)
    else:
        items.sort(key=lambda item: item["assigned_at"] or datetime.min, reverse=True)

    total = len(items)
    offset = (page - 1) * size
    return {
        "items": items[offset:offset + size],
        "counts": counts,
        "total": total,
        "page": page,
        "size": size,
        "total_pages": math.ceil(total / size) if total else 0,
    }


@router.get("/assessments/{practice_id}")
def get_assessment_detail(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assignment = (
        db.query(PracticeAssignment)
        .options(joinedload(PracticeAssignment.practice))
        .filter(
            PracticeAssignment.user_id == current_user.id,
            PracticeAssignment.practice_id == practice_id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    session = _session_by_practice(db, current_user.id).get(practice_id)
    card = _assessment_card(db, assignment, session, _utcnow())
    return {
        **card,
        "eligibility_url": f"/testing/practices/{practice_id}/eligibility",
        "start_url": f"/testing/practices/{practice_id}/sessions",
        "result_url": f"/candidate/portal/reports/{session.session_id}" if session else None,
    }


@router.get("/reports/{session_id}")
def get_report(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(TestSession)
        .options(joinedload(TestSession.practice))
        .filter(TestSession.session_id == session_id, TestSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Report not found")

    assignment = (
        db.query(PracticeAssignment)
        .filter(
            PracticeAssignment.practice_id == session.practice_id,
            PracticeAssignment.user_id == current_user.id,
        )
        .first()
    )

    answers = (
        db.query(UserAnswer)
        .filter(UserAnswer.session_id == session.session_id)
        .order_by(UserAnswer.id.asc())
        .all()
    )
    question_ids = [answer.question_id for answer in answers if answer.question_id]
    questions_by_id = (
        {q.id: q for q in db.query(Question).filter(Question.id.in_(question_ids)).all()}
        if question_ids
        else {}
    )
    category_buckets: dict[str, dict] = {}
    review_items = []
    total_time = 0.0
    for index, answer in enumerate(answers, start=1):
        question = questions_by_id.get(answer.question_id)
        category = question.category if question and question.category else "General"
        bucket = category_buckets.setdefault(category, {"category": category, "answered": 0, "correct": 0})
        bucket["answered"] += 1
        if answer.is_correct:
            bucket["correct"] += 1
        total_time += float(answer.time_spent or 0)
        review_items.append(
            {
                "number": index,
                "question_id": str(answer.question_id) if answer.question_id else None,
                "question_text": question.text if question else None,
                "category": category,
                "is_correct": bool(answer.is_correct),
                "user_answer": answer.user_answer,
                "user_answer_text": _option_text(question, answer.user_answer),
                "correct_answer_id": str(question.correct_answer) if question and question.correct_answer else None,
                "correct_answer_text": _option_text(question, question.correct_answer) if question else None,
                "points_awarded": round(float(answer.points_awarded or 0), 2),
                "time_spent": answer.time_spent,
            }
        )

    categories = [
        {
            "category": bucket["category"],
            "score": _percent((bucket["correct"] / bucket["answered"]) * 100 if bucket["answered"] else 0),
            "answered": bucket["answered"],
            "correct": bucket["correct"],
        }
        for bucket in category_buckets.values()
    ]
    categories.sort(key=lambda item: item["score"], reverse=True)

    peer_scores = [
        float(row[0] or 0)
        for row in db.query(TestSession.overall_points)
        .filter(TestSession.practice_id == session.practice_id, TestSession.is_finished == True)
        .all()
    ]
    score = _percent(session.overall_points)
    lower_or_equal = len([value for value in peer_scores if value <= score])
    percentile = _percent((lower_or_equal / len(peer_scores)) * 100) if peer_scores else 100
    top_label = f"Top {max(1, 100 - percentile)}%"

    weakest = categories[-1]["category"] if categories else "Practice"
    strongest = categories[0]["category"] if categories else "Core Skills"
    return {
        "session_id": str(session.session_id),
        "practice_id": str(session.practice_id),
        "title": session.practice.title if session.practice else "Assessment Report",
        "status": "passed" if score >= 60 else "needs_improvement",
        "score": score,
        "completed_at": assignment.completed_at if assignment and assignment.completed_at else session.started_time,
        "time_taken_seconds": int(total_time),
        "time_taken_label": _format_duration(total_time),
        "percentile": percentile,
        "percentile_label": top_label,
        "performance_by_category": categories,
        "question_review": review_items,
        "ai_insights": {
            "summary": "Based on your answers, here is a breakdown of your skills.",
            "strengths": [
                f"Strong performance in {strongest}.",
                "You completed the assessment with consistent answer quality.",
            ],
            "areas_for_improvement": [
                f"Review edge cases in {weakest}.",
                "Add targeted practice for lower-scoring categories.",
            ],
            "recommended_next_step": {
                "title": f"Advanced {weakest}",
                "duration": "15 min video module",
                "url": f"/learning/{weakest.lower().replace(' ', '-')}",
            },
        },
    }


@router.get("/analytics")
def get_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _analytics_from_sessions(db, current_user.id)


@router.get("/analytics/overview")
def get_analytics_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _analytics_from_sessions(db, current_user.id)


@router.get("/analytics/categories")
def get_analytics_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"items": _analytics_from_sessions(db, current_user.id)["categories"]}


@router.get("/analytics/timeline")
def get_analytics_timeline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"items": _analytics_from_sessions(db, current_user.id)["timeline"]}


@router.get("/notifications")
def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = _notifications_from_cards(db, current_user.id)
    return {
        "items": items,
        "unread_count": len([item for item in items if not item.get("is_read")]),
    }


@router.post("/notifications/read-all")
def mark_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    state = (
        db.query(CandidateNotificationState)
        .filter(CandidateNotificationState.user_id == current_user.id)
        .first()
    )
    if state is None:
        state = CandidateNotificationState(user_id=current_user.id)
        db.add(state)
    state.last_read_at = _utcnow()
    state.updated_at = _utcnow()
    db.commit()
    return {"ok": True, "unread_count": 0, "last_read_at": state.last_read_at}


@router.get("/profile/share")
def get_profile_share_payload(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = _profile_payload(db, current_user)
    return {
        "share_url": f"/candidate/profile/{current_user.id}",
        "profile": payload["profile"],
        "profile_strength": payload["profile_strength"],
        "certificates_url": "/candidate/portal/certificates",
        "analytics_url": "/candidate/portal/analytics",
    }


@router.get("/ai-profile")
def get_ai_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _profile_payload(db, current_user)


@router.patch("/ai-profile")
def update_ai_profile(
    payload: CandidateProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = _ensure_profile(db, current_user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field in {"name", "surname", "email"}:
            setattr(current_user, field, value)
        else:
            setattr(profile, field, value)
    profile.updated_at = _utcnow()
    db.commit()
    return _profile_payload(db, current_user)


@router.post("/profile/avatar")
def upload_profile_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content_type = (file.content_type or "").lower()
    if content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=400, detail="Only PNG, JPG, or WEBP images are supported")

    content = file.file.read()
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="Profile image exceeds 3MB")

    ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }[content_type]
    user_dir = AVATAR_ROOT / str(current_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4()}{ext}"
    path = user_dir / stored_name
    path.write_bytes(content)

    profile = _ensure_profile(db, current_user)
    profile.avatar_url = f"/uploads/avatars/{current_user.id}/{stored_name}"
    profile.updated_at = _utcnow()
    db.commit()
    return _profile_payload(db, current_user)


@router.get("/certificates")
def list_certificates(
    status_filter: str = Query("all", alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if status_filter not in {"all", "verified", "pending"}:
        raise HTTPException(status_code=400, detail="Invalid certificate status")
    all_items = _certificate_items(db, current_user.id, "all")
    items = all_items if status_filter == "all" else [
        item for item in all_items if item["status"] == status_filter
    ]
    return {"items": items, "counts": _certificate_counts(all_items), "total": len(items)}


@router.get("/certificates/{certificate_key}")
def get_certificate(
    certificate_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _find_certificate_item(db, current_user.id, certificate_key)


@router.get("/certificates/{certificate_key}/share")
def get_certificate_share_payload(
    certificate_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = _find_certificate_item(db, current_user.id, certificate_key)
    return {
        "certificate": item,
        "share_url": f"/candidate/certificates/{item['credential_id'] or item['id']}",
        "profile_share_url": f"/candidate/profile/{current_user.id}",
    }


@router.get("/certificates/{certificate_key}/download")
def get_certificate_download_payload(
    certificate_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = _find_certificate_item(db, current_user.id, certificate_key)
    download_url = item.get("download_url") if item.get("source") == "external" else None
    return {
        "certificate": item,
        "download_url": download_url,
        "ready": bool(download_url),
    }


@router.post("/certificates", status_code=status.HTTP_201_CREATED)
def add_external_certificate(
    payload: CertificateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    credential_id = payload.credential_id or f"EXT-{str(uuid.uuid4())[:8].upper()}"
    exists = (
        db.query(CandidateCertificate.id)
        .filter(CandidateCertificate.credential_id == credential_id)
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="Credential ID already exists")

    certificate = CandidateCertificate(
        id=uuid.uuid4(),
        user_id=current_user.id,
        title=payload.title,
        provider=payload.provider,
        issued_at=payload.issued_at,
        status="pending",
        credential_id=credential_id,
        tags=payload.tags,
        file_url=payload.file_url,
        external_url=payload.external_url,
        verification_notes=payload.verification_notes or "Our team is currently verifying this credential with the issuer.",
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(certificate)
    db.commit()
    db.refresh(certificate)
    return _external_certificate_payload(certificate)


@router.delete("/certificates/{certificate_id}")
def delete_external_certificate(
    certificate_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    certificate = (
        db.query(CandidateCertificate)
        .filter(
            CandidateCertificate.id == certificate_id,
            CandidateCertificate.user_id == current_user.id,
        )
        .first()
    )
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")
    db.delete(certificate)
    db.commit()
    return {"id": str(certificate_id), "deleted": True}


@router.get("/resume-reviews/latest")
def get_latest_resume_review(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _resume_review_payload(_latest_resume_review(db, current_user.id))


@router.post("/resume-reviews", status_code=status.HTTP_201_CREATED)
def upload_resume_for_review(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filename = os.path.basename(file.filename or "resume.pdf")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported")

    content = file.file.read()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume file exceeds 5MB")

    user_dir = UPLOAD_ROOT / str(current_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = re.sub(r"[^A-Za-z0-9_.-]", "_", filename)
    stored_name = f"{uuid.uuid4()}_{safe_filename}"
    path = user_dir / stored_name
    path.write_bytes(content)

    text = _extract_resume_text(path)
    analysis = _analyze_resume(text)
    review = CandidateResumeReview(
        id=uuid.uuid4(),
        user_id=current_user.id,
        filename=filename,
        file_url=str(path).replace("\\", "/"),
        score=analysis["score"],
        analysis_summary=analysis["summary"],
        strengths=analysis["strengths"],
        suggestions=analysis["suggestions"],
        created_at=_utcnow(),
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return _resume_review_payload(review)


# ============================================================
# Student panel extras: leaderboard, achievements, practice mode.
#
# These endpoints are additive and read-only (except practice mode,
# which is a stateless next-question feed). They serve the student
# panel's new pages and do not interact with the anti-cheat / adaptive
# difficulty logic in routers/questions.py.
# ============================================================

from sqlalchemy import and_, or_
from datetime import timedelta
import hashlib
import random


def _leaderboard_average_for(db: Session, user_id: uuid.UUID) -> tuple[float, int, Optional[datetime]]:
    """Returns (average_score, completed_sessions, last_activity_at) for a user."""
    sessions = (
        db.query(TestSession)
        .filter(TestSession.user_id == user_id, TestSession.is_finished == True)  # noqa: E712
        .all()
    )
    if not sessions:
        return 0.0, 0, None
    scores: list[int] = []
    last: Optional[datetime] = None
    for s in sessions:
        # We don't store the canonical "percent" so we derive it from
        # user_answers: correct / total.
        rows = (
            db.query(UserAnswer)
            .filter(UserAnswer.session_id == s.session_id)
            .all()
        )
        if rows:
            correct = sum(1 for r in rows if r.is_correct)
            scores.append(round(100 * correct / len(rows)))
        if s.started_time and (last is None or s.started_time > last):
            last = s.started_time
    average = round(sum(scores) / len(scores), 1) if scores else 0.0
    return average, len(sessions), last


@router.get("/leaderboard")
def get_leaderboard(
    scope: str = Query("group", pattern=r"^(group|global)$"),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ranks students by average score across their finished sessions.

    Other students are anonymised (initials + group); the current user
    sees their own row by full name. `scope=group` restricts the board
    to users sharing the same `group_name`; `scope=global` includes
    everyone.
    """
    query = db.query(User).filter(User.role == "USER")
    if scope == "group" and current_user.group_name:
        query = query.filter(User.group_name == current_user.group_name)
    users = query.all()

    rows: list[dict] = []
    for user in users:
        avg, sessions_count, last_activity = _leaderboard_average_for(db, user.id)
        if sessions_count == 0:
            continue
        is_self = user.id == current_user.id
        display = (
            _full_name(user)
            if is_self
            else (f"{(user.name or '')[:1]}{(user.surname or '')[:1]}".upper() or "ST")
        )
        rows.append({
            "user_id": str(user.id) if is_self else None,
            "display_name": display,
            "is_self": is_self,
            "group_name": user.group_name,
            "average_score": avg,
            "completed_sessions": sessions_count,
            "last_activity_at": last_activity,
        })

    rows.sort(key=lambda r: (-r["average_score"], -r["completed_sessions"]))
    you_rank: Optional[int] = None
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
        if row["is_self"]:
            you_rank = index

    return {
        "scope": scope,
        "group_name": current_user.group_name if scope == "group" else None,
        "items": rows[:limit],
        "you_rank": you_rank,
        "total_ranked": len(rows),
    }


def _badge(
    badge_id: str,
    title: str,
    description: str,
    tier: str,
    progress: int,
    target: int,
) -> dict:
    return {
        "id": badge_id,
        "title": title,
        "description": description,
        "tier": tier,
        "earned": progress >= target,
        "progress": min(progress, target),
        "target": target,
    }


@router.get("/achievements")
def get_achievements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Derived gamification badges based on the student's sessions,
    certificates, and activity. All checks are read-only — nothing is
    stored server-side, so the response is recomputed on each request.
    """
    finished_sessions = (
        db.query(TestSession)
        .filter(
            TestSession.user_id == current_user.id,
            TestSession.is_finished == True,  # noqa: E712
        )
        .order_by(TestSession.started_time.desc())
        .all()
    )

    # Per-session percent score (correct/total) so we can spot perfect runs.
    perfect_count = 0
    high_count = 0
    score_total = 0
    for s in finished_sessions:
        answers = (
            db.query(UserAnswer)
            .filter(UserAnswer.session_id == s.session_id)
            .all()
        )
        if not answers:
            continue
        correct = sum(1 for r in answers if r.is_correct)
        percent = round(100 * correct / len(answers))
        score_total += percent
        if percent == 100:
            perfect_count += 1
        if percent >= 80:
            high_count += 1

    average_score = (
        round(score_total / len(finished_sessions), 1) if finished_sessions else 0.0
    )

    # Crude streak: count distinct calendar days with at least one finished
    # session in the last 30 days, working backwards from today.
    today = datetime.utcnow().date()
    completed_days = {
        s.started_time.date()
        for s in finished_sessions
        if s.started_time and (today - s.started_time.date()).days < 60
    }
    streak = 0
    cursor = today
    while cursor in completed_days:
        streak += 1
        cursor = cursor - timedelta(days=1)

    cert_count = (
        db.query(CandidateCertificate)
        .filter(CandidateCertificate.user_id == current_user.id)
        .count()
    )

    badges = [
        _badge(
            "first_steps",
            "First Steps",
            "Complete your first assessment.",
            "bronze",
            min(len(finished_sessions), 1),
            1,
        ),
        _badge(
            "consistent_learner",
            "Consistent Learner",
            "Finish 5 assessments.",
            "silver",
            min(len(finished_sessions), 5),
            5,
        ),
        _badge(
            "perfect_score",
            "Perfect Score",
            "Score 100% on any assessment.",
            "gold",
            min(perfect_count, 1),
            1,
        ),
        _badge(
            "high_scorer",
            "High Scorer",
            "Score 80% or higher on 5 assessments.",
            "silver",
            min(high_count, 5),
            5,
        ),
        _badge(
            "streak_starter",
            "Streak Starter",
            "Complete an assessment on 3 consecutive days.",
            "bronze",
            min(streak, 3),
            3,
        ),
        _badge(
            "certified",
            "Certified",
            "Earn 3 certificates.",
            "gold",
            min(cert_count, 3),
            3,
        ),
    ]

    earned = sum(1 for b in badges if b["earned"])
    return {
        "summary": {
            "completed_assessments": len(finished_sessions),
            "perfect_scores": perfect_count,
            "average_score": average_score,
            "certificates": cert_count,
            "current_streak_days": streak,
        },
        "badges": badges,
        "earned_count": earned,
        "total_count": len(badges),
    }


@router.get("/practice/categories")
def get_practice_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lists practice question categories available to the student
    (categories that appear in any practice they're assigned to).
    """
    assignments = (
        db.query(PracticeAssignment)
        .filter(PracticeAssignment.user_id == current_user.id)
        .all()
    )
    practice_ids = [a.practice_id for a in assignments]
    if not practice_ids:
        # Fall back to global categories so the page isn't empty for a
        # student who hasn't been assigned yet.
        all_categories = (
            db.query(Question.category, func.count(Question.id))
            .filter(Question.category.isnot(None))
            .group_by(Question.category)
            .all()
        )
        return {"items": [{"category": c, "question_count": n} for c, n in all_categories if c]}

    practices = (
        db.query(Practice)
        .filter(Practice.practice_id.in_(practice_ids))
        .all()
    )
    question_ids: set[uuid.UUID] = set()
    for practice in practices:
        for qid in practice.question_ids or []:
            question_ids.add(qid)
    if not question_ids:
        return {"items": []}

    rows = (
        db.query(Question.category, func.count(Question.id))
        .filter(Question.id.in_(question_ids), Question.category.isnot(None))
        .group_by(Question.category)
        .all()
    )
    return {"items": [{"category": c, "question_count": n} for c, n in rows if c]}


@router.get("/practice/next-question")
def get_practice_next_question(
    category: Optional[str] = Query(None, max_length=64),
    difficulty: Optional[str] = Query(None, pattern=r"^(easy|medium|hard)$"),
    exclude_ids: Optional[str] = Query(
        None,
        description="Comma-separated question UUIDs the client already saw.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns a single random practice question (with its correct
    answer baked in so the client can grade locally). This endpoint is
    NOT for graded tests — it is the untimed practice lab.

    The student gets a fresh, deterministic shuffle of options per
    question per session by re-using the seeded shuffle from the
    questions router; here we just pick a question matching the
    filters that isn't in `exclude_ids`.
    """
    excluded: set[uuid.UUID] = set()
    if exclude_ids:
        for raw in exclude_ids.split(","):
            try:
                excluded.add(uuid.UUID(raw.strip()))
            except (TypeError, ValueError):
                continue

    query = db.query(Question)
    if category:
        query = query.filter(Question.category == category)
    if difficulty:
        # difficulty_level is a float; map 'easy'/'medium'/'hard' to
        # rough buckets so the client filter is meaningful.
        if difficulty == "easy":
            query = query.filter(Question.difficulty_level <= 0.35)
        elif difficulty == "medium":
            query = query.filter(
                and_(Question.difficulty_level > 0.35, Question.difficulty_level <= 0.7)
            )
        else:
            query = query.filter(Question.difficulty_level > 0.7)
    if excluded:
        query = query.filter(~Question.id.in_(excluded))

    candidates = query.all()
    if not candidates:
        return {"event": "exhausted", "question": None}

    pick = random.choice(candidates)
    # Stable per-user option shuffle so a student sees the same order
    # if they revisit the same question on the same day.
    seed_input = f"{current_user.id}:{pick.id}:{datetime.utcnow().date().isoformat()}"
    seed = int(hashlib.sha256(seed_input.encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    options = list(pick.options or [])
    rng.shuffle(options)

    return {
        "event": "practice_question",
        "question": {
            "id": str(pick.id),
            "text": pick.text,
            "options": options,
            "category": pick.category,
            "difficulty_level": pick.difficulty_level,
            "correct_answer": str(pick.correct_answer),
        },
    }
