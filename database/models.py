import uuid
from datetime import datetime, timedelta
from sqlalchemy import JSON, Column, Date, Integer, String, ForeignKey, Boolean, Text, Float, DateTime, Enum as SAEnum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSON
from sqlalchemy.sql import func

# Ensure these imports match your project structure
from database.database import Base
from database.enums import Role

# --- Company Model ---
class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False)
    phone_number = Column(String(20))
    INN = Column(String(20))
    email = Column(String(100), unique=True)

    # Relationships
    users = relationship("User", back_populates="company")
    created_vacancies = relationship("Created_Vacancy", back_populates="company")
    
    # FIX: The model 'StartedTest' does not exist. 
    # Removed the incorrect relationship definition here.
    # assigned_tests = relationship("StartedTest", back_populates="owner_company")

# --- User Model ---
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(30), unique=True, nullable=False)
    role = Column(SAEnum(Role), default=Role.USER, nullable=False)
    password = Column(String(100), nullable=False)
    
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    company = relationship("Company", back_populates="users")

    # Profile fields
    name = Column(String(30), nullable=False)
    surname = Column(String(30), nullable=False)
    age = Column(Integer, nullable=False)
    email = Column(String(100), nullable=True)
    group_name = Column(String(50), nullable=True, index=True)

    # Relationships
    # FIX: Changed relationship target from StartedTest (old model) to TestSession (new model)
    test_sessions = relationship("TestSession", back_populates="user")
    candidate_profile = relationship("CandidateProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    certificates = relationship("CandidateCertificate", back_populates="user", cascade="all, delete-orphan")
    resume_reviews = relationship("CandidateResumeReview", back_populates="user", cascade="all, delete-orphan")
    
    # Removed the redundant or incorrect user_answers relationship here, 
    # as the answers are linked via TestSession.

# --- Created_Vacancy Model ---
class Created_Vacancy(Base):
    __tablename__ = 'created_vacancies'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_name = Column(String(100), nullable=False)
    job_description = Column(Text, nullable=False)
    tag = Column(Text, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    candidate_count = Column(Integer, default=0)
    is_available = Column(Boolean, default=True)

    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"))
    company = relationship("Company", back_populates="created_vacancies")

    candidates = relationship("Candidate", back_populates="vacancy")

    
class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # --- NEW COLUMNS ---
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(String(50), default="Applied") # E.g., "Applied", "Testing", "Interview", "Rejected"
    # -------------------
    
    full_name = Column(String(100), nullable=False)
    resume_loc = Column(String(255), nullable=False)
    ai_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=func.now())
    education = Column(String(255))
    experience = Column(String(255))
    skills = Column(String(255))

    vacancy_id = Column(UUID(as_uuid=True), ForeignKey("created_vacancies.id"))
    vacancy = relationship("Created_Vacancy", back_populates="candidates")
    user = relationship("User") # Add relationship to User


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    avatar_url = Column(String(255), nullable=True)
    headline = Column(String(150), nullable=True)
    location = Column(String(100), nullable=True)
    university = Column(String(150), nullable=True)
    graduation_year = Column(String(10), nullable=True)
    phone = Column(String(30), nullable=True)
    portfolio_url = Column(String(255), nullable=True)
    linkedin_url = Column(String(255), nullable=True)
    open_to_work = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="candidate_profile")


class CandidateNotificationState(Base):
    __tablename__ = "candidate_notification_state"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_read_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="notification_state")


class CandidateCertificate(Base):
    __tablename__ = "candidate_certificates"
    __table_args__ = (
        Index("ix_candidate_certificates_user_status", "user_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(150), nullable=False)
    provider = Column(String(150), nullable=True)
    issued_at = Column(Date, nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    credential_id = Column(String(80), nullable=True, unique=True)
    badge_label = Column(String(60), nullable=True)
    tags = Column(ARRAY(String), nullable=False, default=list)
    file_url = Column(String(255), nullable=True)
    external_url = Column(String(255), nullable=True)
    verification_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="certificates")


class CandidateResumeReview(Base):
    __tablename__ = "candidate_resume_reviews"
    __table_args__ = (
        Index("ix_candidate_resume_reviews_user_created", "user_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_url = Column(String(255), nullable=True)
    score = Column(Float, default=0.0)
    analysis_summary = Column(Text, nullable=True)
    strengths = Column(JSON, nullable=False, default=list)
    suggestions = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="resume_reviews")
#### TESTING PART

# --- Question Model ---
# Add this to your models file
class QuestionHistory(Base):
    __tablename__ = "question_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(UUID(as_uuid=True), ForeignKey("user_questions.id"), nullable=False)
    
    # Store what changed
    old_difficulty = Column(Float)
    new_difficulty = Column(Float)
    change_reason = Column(String) # e.g., "AI recalibration" or "Admin manual update"
    
    changed_at = Column(DateTime, server_default=func.now())
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    question = relationship("Question", back_populates="history")

class Question(Base):
    __tablename__ = "user_questions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text = Column(String, nullable=False)
    
    # CHANGE 1: This stores the UUID of the correct option, not the text "A" or "WHERE"
    correct_answer = Column(UUID(as_uuid=True), nullable=False) 
    
    # CHANGE 2: This will now store a LIST of objects, not a dictionary
    options = Column(JSON, nullable=False) 
    history = relationship("QuestionHistory", back_populates="question", cascade="all, delete-orphan")
    difficulty_level = Column(Float, default=0.5)
    category = Column(String(50))
    points = Column(Float, default=1.0)
class Practice(Base):
    __tablename__ = "practice"
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    practice_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    question_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False) 
    tags = Column(ARRAY(String), nullable=False)
    allowed_users = relationship("User", secondary="practice_assignments", backref="assigned_practices")
    duration_minutes = Column(Integer, nullable=False, default=30)
    description = Column(String, nullable=False, default="")

    # --- CHANGE END ---

    deadline = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_valid = Column(Boolean, default=True)
    
    test_sessions = relationship("TestSession", back_populates="practice")
# New Association Table
class PracticeAssignment(Base):
    __tablename__ = "practice_assignments"
    assignment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    practice_id = Column(UUID(as_uuid=True), ForeignKey("practice.practice_id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)

    # Association-object relationships. The `overlaps` directive silences the
    # SQLAlchemy warning about overlapping with Practice.allowed_users (which
    # uses this table as `secondary`).
    user = relationship("User", overlaps="allowed_users,assigned_practices")
    practice = relationship("Practice", overlaps="allowed_users,assigned_practices")


class TestSession(Base):
    __tablename__ = "test_session"
    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    practice_id = Column(UUID(as_uuid=True), ForeignKey("practice.practice_id"), nullable=False)
    practice = relationship("Practice", back_populates="test_sessions") # Added relationship to Practice
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="test_sessions") # Added relationship to User
    
    overall_points = Column(Float, default=0.0)
    is_finished = Column(Boolean, default=False)
    started_time = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to track individual answers
    answers = relationship("UserAnswer", back_populates="session")

class UserAnswer(Base):
    __tablename__ = "user_answers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    session_id = Column(UUID(as_uuid=True), ForeignKey("test_session.session_id"))
    session = relationship("TestSession", back_populates="answers") # Relationship to TestSession

    question_id = Column(UUID(as_uuid=True), ForeignKey("user_questions.id"))
    user_answer = Column(String)
    is_correct = Column(Boolean)
    points_awarded = Column(Float)
    time_spent = Column(Float, nullable=True)


# ============================================================
# Anti-cheat + per-student adaptive difficulty (sidecar tables).
#
# Stored in separate tables instead of ALTERing `users` / `test_session`
# so that existing endpoints keep working even before the SQL migration
# in db/anticheat_schema.sql is run on the database. SQLAlchemy
# relationships are lazy, so these are only queried by the anti-cheat
# code paths.
# ============================================================

class UserSkill(Base):
    """Per-user running skill estimate (0..1). Drives adaptive question
    selection — the test serves the unanswered question whose
    `difficulty_level` is closest to this value."""
    __tablename__ = "user_skills"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_estimate = Column(Float, nullable=False, default=0.5)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = relationship("User", backref="skill")


class TestSessionMeta(Base):
    """Anti-cheat sidecar for a TestSession: the shuffled, locked
    question order for resume support, the connection fingerprint
    captured at session start, and the rolling strike counter used by
    POST /testing/sessions/{id}/events."""
    __tablename__ = "test_session_meta"

    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("test_session.session_id", ondelete="CASCADE"),
        primary_key=True,
    )
    question_order = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    device_fingerprint = Column(String(128), nullable=True)
    strikes = Column(Integer, nullable=False, default=0)
    auto_finished_reason = Column(String(64), nullable=True)

    session = relationship(
        "TestSession",
        back_populates="meta",
    )


# Wire the back-side of TestSession <-> TestSessionMeta after both
# classes exist so we don't have to ALTER the TestSession class body
# above (keeps the diff smaller and the back-compat story cleaner).
TestSession.meta = relationship(
    "TestSessionMeta",
    uselist=False,
    cascade="all, delete-orphan",
    back_populates="session",
)


class SessionEvent(Base):
    """Anti-cheat event ingested from the test page (tab_blur,
    paste_attempt, devtools_open, fullscreen_exit, copy_attempt,
    right_click, suspicious_timing, ...). Severity drives the strike
    counter on TestSessionMeta."""
    __tablename__ = "session_events"
    __table_args__ = (
        Index("ix_session_events_session_id", "session_id"),
        Index("ix_session_events_event_type", "event_type"),
        Index("ix_session_events_severity", "severity"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("test_session.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = Column(String(64), nullable=False)
    severity = Column(String(16), nullable=False, default="info")
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("TestSession", backref="events")


# ============================================================
# AI interview (text-chat interviewer powered by OpenAI).
#
# These tables are intentionally light: one row per interview session
# (status, role/topic, optional final grade) plus one row per chat
# turn (role + content). The grading payload is stored as JSON so we
# can evolve the rubric without a schema change.
# ============================================================

class AIInterviewSession(Base):
    __tablename__ = "ai_interview_sessions"
    __table_args__ = (
        Index("ix_ai_interview_sessions_user", "user_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Role / topic the interviewer is hiring for, e.g. "Frontend Engineer".
    role = Column(String(120), nullable=False)
    # Free-form context the student or admin pasted in (a JD, a CV
    # excerpt, etc.). Optional.
    context = Column(Text, nullable=True)
    # active | finished | abandoned
    status = Column(String(20), nullable=False, default="active")
    # Filled in by the final grading step. Free-form numeric 0..100.
    final_score = Column(Float, nullable=True)
    # Structured grading dump: { score, strengths[], improvements[],
    # summary, skill_breakdown[] }. JSON so we can iterate on the rubric.
    final_feedback = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)

    messages = relationship(
        "AIInterviewMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AIInterviewMessage.created_at",
    )


class AIInterviewMessage(Base):
    __tablename__ = "ai_interview_messages"
    __table_args__ = (
        Index("ix_ai_interview_messages_session_created", "session_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # system | user | assistant. The system message is the interviewer
    # prompt and is hidden from the chat transcript on the frontend.
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("AIInterviewSession", back_populates="messages")
