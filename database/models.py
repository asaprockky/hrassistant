from database.database import Base
from sqlalchemy import JSON, Column, Date, Integer, String, ForeignKey, Boolean, Text, Float, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from sqlalchemy.sql import func

# --- Company Model ---
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    phone_number = Column(String(20))
    INN = Column(String(20))
    email = Column(String(100), unique=True)

    # Relationships
    users = relationship("User", back_populates="company")
    created_vacancies = relationship("Created_Vacancy", back_populates="company")

# --- User Model ---
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(30), unique=True, nullable=False)
    role = Column(String(30))
    password = Column(String(100), nullable=False)

    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    company = relationship("Company", back_populates="users")

    # Relationship to StartedTest
    started_tests = relationship("StartedTest", back_populates="user")
    user_answers = relationship("UserAnswer", back_populates="user")

# --- Created_Vacancy Model ---
class Created_Vacancy(Base):
    __tablename__ = 'created_vacancies'

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String(100), nullable=False)
    job_description = Column(Text, nullable=False)
    tag = Column(Text, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    candidate_count = Column(Integer, default=0)
    is_available = Column(Boolean, default=True)

    company_id = Column(Integer, ForeignKey("companies.id"))
    company = relationship("Company", back_populates="created_vacancies")

    # Relationship with candidates
    candidates = relationship("Candidate", back_populates="vacancy")

# --- Candidate Model ---
class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    resume_loc = Column(String(255), nullable=False)
    ai_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=func.now()) # Use DateTime and func.now() for better database tracking
    education = Column(String(255))
    experience = Column(String(255))
    skills = Column(String(255))

    vacancy_id = Column(Integer, ForeignKey("created_vacancies.id"))
    vacancy = relationship("Created_Vacancy", back_populates="candidates")

    # Relationship to answers

# --- Question Model (The Single, Correct Definition) ---
class Question(Base):
    __tablename__ = "user_questions"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, nullable=False)
    difficulty_level = Column(Integer, nullable=False) # 1-9
    correct_answer = Column(String, nullable=False)
    options = Column(JSON) # e.g. ["option1", "option2", ...]
    category = Column(String(50)) # e.g. math, python
    points = Column(Float)

    # Relationship to answers
    user_answers = relationship("UserAnswer", back_populates="question")

# --- UserAnswer Model ---
class UserAnswer(Base):
    __tablename__ = "user_answers"

    id = Column(Integer, primary_key=True, index=True)
    user_answer = Column(String, nullable=False)
    is_correct = Column(Boolean, nullable=False) # Tracks correctness
    score_awarded = Column(Float, default=0.0) # Tracks points awarded for the answer
    
    user_id = Column(Integer, ForeignKey("users.id"))
    question_id = Column(Integer, ForeignKey("user_questions.id"))
    
    answered_at = Column(DateTime, default=func.now()) # When the answer was recorded

    # Relationships
    user = relationship("User", back_populates="user_answers")
    question = relationship("Question", back_populates="user_answers")


class StartedTest(Base):
    __tablename__ = "started_test"

    test_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id")) 
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="started_tests")