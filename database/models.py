# models.py
import uuid
from datetime import datetime
from sqlalchemy import JSON, Column, Date, Integer, String, ForeignKey, Boolean, Text, Float, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
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
    assigned_tests = relationship("StartedTest", back_populates="owner_company")

# --- User Model ---
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(30), unique=True, nullable=False)
    role = Column(SAEnum(Role), default=Role.USER, nullable=False)
    password = Column(String(100), nullable=False)
    
    # FIXED: Type must match Company.id (UUID)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    company = relationship("Company", back_populates="users")

    # Profile fields
    name = Column(String(30), nullable=False)
    surname = Column(String(30), nullable=False)
    age = Column(Integer, nullable=False)
    email = Column(String(30), nullable=True)

    # Relationships
    started_tests = relationship("StartedTest", back_populates="user")
    user_answers = relationship("UserAnswer", back_populates="user")


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

    # FIXED: Type must match Company.id (UUID)
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

    # FIXED: Type must match Created_Vacancy.id (UUID)
    vacancy_id = Column(UUID(as_uuid=True), ForeignKey("created_vacancies.id"))
    vacancy = relationship("Created_Vacancy", back_populates="candidates")

# --- Question Model ---
class Question(Base):
    __tablename__ = "user_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text = Column(String, nullable=False)
    difficulty_level = Column(Integer, nullable=False)
    correct_answer = Column(String, nullable=False)
    options = Column(JSON)
    category = Column(String(50))
    points = Column(Float)

    user_answers = relationship("UserAnswer", back_populates="question")

# --- UserAnswer Model ---
class UserAnswer(Base):
    __tablename__ = "user_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_answer = Column(String, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    score_awarded = Column(Float, default=0.0)
    
    # FIXED: Types must match User.id and Question.id (UUID)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("user_questions.id"))
    
    answered_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="user_answers")
    question = relationship("Question", back_populates="user_answers")

# --- Started Test Model ---
class StartedTest(Base):
    __tablename__ = "started_test"

    test_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # FIXED: Types must match User.id and Company.id (UUID)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id")) 
    owner = Column(UUID(as_uuid=True), ForeignKey("companies.id"))
    
    deadline = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    current_level = Column(Integer, default=1)
    current_score = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="started_tests")
    owner_company = relationship("Company")