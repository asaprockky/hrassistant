from datetime import date, datetime
from typing import List, Optional
import uuid
from database.enums import Role
from pydantic import BaseModel, ConfigDict, EmailStr


class TestSessionItem(BaseModel):
    testId: str
    title: str
    createdBy: str
    createdAt: datetime
    deadline: Optional[datetime] = None 
    score: int
    status: str
    statusLabel: str
    actionUrl: str

    class Config:
        from_attributes = True

class PaginatedTests(BaseModel):
    items: List[TestSessionItem]
    total: int
    page: int
    size: int
    totalPages: int
class ApplicationSummary(BaseModel):
    candidate_id: uuid.UUID
    vacancy_id: uuid.UUID
    company_name: str
    position_title: str
    status: str
    ai_fit_score: int # We will pass this as an integer percentage
    applied_at: str

class PaginatedApplications(BaseModel):
    items: List[ApplicationSummary]
    total: int
    page: int
    size: int
    total_pages: int

class PipelineStats(BaseModel):
    total_jobs_applied: int
    total_tests_completed: int
    average_test_score: int

class CandidateDashboardOut(BaseModel):
    pipeline_overview: PipelineStats
    recent_applications: List[ApplicationSummary]
# --- Base Configuration ---
# In Pydantic v2, we can use a base class to handle ORM mode for everyone
class BaseORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# --- Company Schemas ---
class CompanyOut(BaseORMModel):
    id: uuid.UUID  # CHANGED: int -> uuid.UUID
    name: str
    phone_number: Optional[str] = None
    INN: Optional[str] = None
    email: Optional[EmailStr] = None

# --- User & Profile Schemas ---
class UserProfileOut(BaseORMModel):
    name: str
    surname: str
    username: str
    age: int
    email: Optional[EmailStr] = None

class UserProfilePageOut(BaseORMModel):
    id: uuid.UUID  # CHANGED: int -> uuid.UUID
    username: str
    role: Role
    company: Optional[CompanyOut] = None
    profile: Optional[UserProfileOut] = None

class UserCreate(BaseModel):
    username: str
    password: str
    role: Role
    name: str
    surname: str
    age: int
    email: Optional[str] = None

class EmailUpdate(BaseModel):
    email: str

class UserResponse(BaseORMModel):
    id: uuid.UUID  # CHANGED: int -> uuid.UUID
    username: str

# --- Vacancy Schemas ---
class VacancyResponse(BaseORMModel):
    id: uuid.UUID  # CHANGED: int -> uuid.UUID
    job_name: str
    job_description: str
    tag: str
    start_date: date
    end_date: date
    company_id: Optional[uuid.UUID] = None  # CHANGED: int -> uuid.UUID

# --- Question & Admin Schemas (NEW) ---

class OptionSchema(BaseModel):
    id: uuid.UUID
    text: str

class QuestionHistoryOut(BaseORMModel):
    id: uuid.UUID
    question_id: uuid.UUID
    old_difficulty: Optional[float]
    new_difficulty: Optional[float]
    change_reason: Optional[str]
    changed_at: datetime
    changed_by: Optional[uuid.UUID]

class QuestionOut(BaseORMModel):
    id: uuid.UUID
    text: str
    options: List[OptionSchema]  # Pydantic will parse the JSONB from DB into this list
    correct_answer: uuid.UUID
    difficulty_level: float
    category: Optional[str]
    points: float

class DifficultyUpdate(BaseModel):
    new_difficulty: float
    change_reason: str = "Manual adjustment"

# --- Testing & Assignment Schemas ---

class AnswerCreate(BaseModel):
    question_id: uuid.UUID
    user_answer: str  # Stores the Option ID
    time_spent: float

class TestStatusResponse(BaseModel):
    message: str
    is_correct: bool
    correct_answer: Optional[str] = None
    points_awarded: float
    is_test_finished: bool

class PracticeCreate(BaseModel):
    title: str
    description: Optional[str] = None
    duration_minutes: int
    deadline: datetime
    question_ids: List[uuid.UUID]
    tags: List[str] = []

class AssignmentUpdate(BaseModel):
    add_user_ids: List[uuid.UUID] = []     # Users to assign
    remove_user_ids: List[uuid.UUID] = []  # Users to de-assign
