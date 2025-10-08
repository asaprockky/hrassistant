from database.database import Base
from sqlalchemy import Column, Date, Integer, String, ForeignKey, Boolean, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime


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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(30), unique=True, nullable=False)
    role = Column(String(30))
    password = Column(String(100), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"))
    company = relationship("Company", back_populates="users")


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


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    resume_loc = Column(String(255), nullable=False)  # File path or URL
    ai_score = Column(Float, default=0.0)
    created_at = Column(Date, default=datetime.utcnow)
    education = Column(String(255))
    experience = Column(String(255))
    skills = Column(String(255))

    vacancy_id = Column(Integer, ForeignKey("created_vacancies.id"))
    vacancy = relationship("Created_Vacancy", back_populates="candidates")
