from datetime import date, datetime
from typing import List, Optional
import uuid
from database.enums import Role
from pydantic import BaseModel, ConfigDict, EmailStr, Field



class UserSearchItem(BaseModel):
    id: uuid.UUID
    name: str
    surname: str
    username: str
    group_name: Optional[str] = None

class PaginatedUserResponse(BaseModel):
    items: List[UserSearchItem]
    total_items: int
    page: int
    size: int
    total_pages: int

class CandidateCreate(BaseModel):
    name: str = Field(..., max_length=30)
    surname: str = Field(..., max_length=30)
    age: int
    email: Optional[str] = None
    group_name: Optional[str] = None

class CandidateCreatedResponse(BaseModel):
    id: uuid.UUID
    username: str
    password: str  # We return the raw password ONLY ONCE here so admin can copy it
    group_name: Optional[str]

class AdvancedAssignmentUpdate(BaseModel):
    add_user_ids: List[uuid.UUID] = []
    add_groups: List[str] = []
    remove_user_ids: List[uuid.UUID] = []
    remove_groups: List[str] = []

        
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


# --- Admin Panel Schemas ---

class AdminDashboardSummary(BaseModel):
    total_users: int
    total_candidates: int
    total_vacancies: int
    active_vacancies: int
    total_practices: int
    active_practices: int
    total_questions: int
    active_test_sessions: int
    completed_test_sessions: int
    average_test_score: int

class AdminUserOut(BaseORMModel):
    id: uuid.UUID
    username: str
    role: Role
    name: str
    surname: str
    age: int
    email: Optional[EmailStr] = None
    company_id: Optional[uuid.UUID] = None

class AdminVacancyOut(BaseORMModel):
    id: uuid.UUID
    job_name: str
    job_description: str
    tag: str
    start_date: date
    end_date: date
    company_id: Optional[uuid.UUID] = None
    candidate_count: Optional[int] = 0
    is_available: Optional[bool] = True

class AdminCandidateOut(BaseORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    vacancy_id: Optional[uuid.UUID] = None
    full_name: str
    status: str
    resume_loc: str
    ai_score: float
    created_at: Optional[datetime] = None
    education: Optional[str] = None
    experience: Optional[str] = None
    skills: Optional[str] = None

class CandidateStatusUpdate(BaseModel):
    status: str

class PracticeOut(BaseORMModel):
    practice_id: uuid.UUID
    title: str
    description: Optional[str] = None
    duration_minutes: int
    deadline: datetime
    question_ids: List[uuid.UUID]
    tags: List[str]
    is_valid: bool
    created_at: datetime

class PracticeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    deadline: Optional[datetime] = None
    question_ids: Optional[List[uuid.UUID]] = None
    tags: Optional[List[str]] = None
    is_valid: Optional[bool] = None

class PracticeAssignmentOut(BaseORMModel):
    assignment_id: uuid.UUID
    practice_id: uuid.UUID
    user_id: uuid.UUID
    assigned_at: datetime
    is_completed: bool
    completed_at: Optional[datetime] = None

class AdminTestSessionOut(BaseORMModel):
    session_id: uuid.UUID
    practice_id: uuid.UUID
    user_id: uuid.UUID
    overall_points: float
    is_finished: bool
    started_time: datetime

class AdminUserAnswerOut(BaseORMModel):
    id: uuid.UUID
    session_id: Optional[uuid.UUID] = None
    question_id: Optional[uuid.UUID] = None
    user_answer: Optional[str] = None
    is_correct: Optional[bool] = None
    points_awarded: Optional[float] = None
    time_spent: Optional[float] = None
