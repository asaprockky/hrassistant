import uuid
from datetime import datetime, timedelta
from sqlalchemy import JSON, Column, Date, Integer, String, ForeignKey, Boolean, Text, Float, DateTime, Enum as SAEnum
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
    email = Column(String(30), nullable=True)

    # Relationships
    # FIX: Changed relationship target from StartedTest (old model) to TestSession (new model)
    test_sessions = relationship("TestSession", back_populates="user")
    
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

# --- Candidate Model ---
class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(100), nullable=False)
    resume_loc = Column(String(255), nullable=False)
    ai_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=func.now())
    education = Column(String(255))
    experience = Column(String(255))
    skills = Column(String(255))

    vacancy_id = Column(UUID(as_uuid=True), ForeignKey("created_vacancies.id"))
    vacancy = relationship("Created_Vacancy", back_populates="candidates")


#### TESTING PART

# --- Question Model ---
class Question(Base):
    __tablename__ = "user_questions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text = Column(String, nullable=False)
    
    # CHANGE 1: This stores the UUID of the correct option, not the text "A" or "WHERE"
    correct_answer = Column(UUID(as_uuid=True), nullable=False) 
    
    # CHANGE 2: This will now store a LIST of objects, not a dictionary
    options = Column(JSON, nullable=False) 
    
    difficulty_level = Column(Integer, nullable=False)
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