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
    add_user_ids: List[uuid.UUID] = Field(default_factory=list)
    add_groups: List[str] = Field(default_factory=list)
    remove_user_ids: List[uuid.UUID] = Field(default_factory=list)
    remove_groups: List[str] = Field(default_factory=list)
    send_invitation: bool = False
    frontend_test_base_url: Optional[str] = None
    invitation_message: Optional[str] = None

        
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

class QuestionOptionCreate(BaseModel):
    id: Optional[uuid.UUID] = None
    text: str = Field(..., min_length=1)

class QuestionCreate(BaseModel):
    text: str = Field(..., min_length=1)
    options: List[QuestionOptionCreate] = Field(..., min_length=2)
    correct_answer: Optional[uuid.UUID] = None
    correct_option_index: Optional[int] = Field(None, ge=0)
    difficulty_level: float = Field(0.5, ge=0, le=1)
    category: Optional[str] = None
    points: float = Field(1.0, gt=0)

class QuestionUpdate(BaseModel):
    text: Optional[str] = Field(None, min_length=1)
    options: Optional[List[QuestionOptionCreate]] = Field(None, min_length=2)
    correct_answer: Optional[uuid.UUID] = None
    correct_option_index: Optional[int] = Field(None, ge=0)
    difficulty_level: Optional[float] = Field(None, ge=0, le=1)
    category: Optional[str] = None
    points: Optional[float] = Field(None, gt=0)

class QuestionHistoryOut(BaseORMModel):
    id: uuid.UUID
    question_id: uuid.UUID
    question_text: Optional[str] = None
    old_difficulty: Optional[float]
    new_difficulty: Optional[float]
    change_reason: Optional[str]
    changed_at: datetime
    changed_by: Optional[uuid.UUID]
    changed_by_name: Optional[str] = None
    changed_by_username: Optional[str] = None

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

class AdminStudentStats(BaseModel):
    id: uuid.UUID
    username: str
    name: str
    surname: str
    email: Optional[EmailStr] = None
    group_name: Optional[str] = None
    assigned_tests: int
    completed_assignments: int
    pending_assignments: int
    active_sessions: int
    completed_sessions: int
    average_score: int
    last_activity_at: Optional[datetime] = None

class AdminStudentStatsResponse(BaseModel):
    items: List[AdminStudentStats]
    total: int
    offset: int
    limit: int

class AdminUserOut(BaseORMModel):
    id: uuid.UUID
    username: str
    role: Role
    name: str
    surname: str
    age: int
    email: Optional[EmailStr] = None
    company_id: Optional[uuid.UUID] = None
    group_name: Optional[str] = None

class AdminUserCreate(BaseModel):
    username: Optional[str] = Field(None, max_length=30)
    password: Optional[str] = Field(None, min_length=4)
    role: Role = Role.USER
    name: str = Field(..., max_length=30)
    surname: str = Field(..., max_length=30)
    age: int = Field(..., ge=0)
    email: Optional[EmailStr] = None
    company_id: Optional[uuid.UUID] = None
    group_name: Optional[str] = Field(None, max_length=50)
    practice_id: Optional[uuid.UUID] = None
    send_invitation: bool = False
    frontend_test_base_url: Optional[str] = None

class AdminBulkUserCreateItem(BaseModel):
    username: Optional[str] = Field(None, max_length=30)
    name: str = Field(..., max_length=30)
    surname: str = Field(..., max_length=30)
    age: int = Field(18, ge=0)
    email: EmailStr
    group_name: Optional[str] = Field(None, max_length=50)

class AdminBulkUserCreate(BaseModel):
    users: List[AdminBulkUserCreateItem] = Field(..., min_length=1)
    role: Role = Role.USER
    company_id: Optional[uuid.UUID] = None
    group_name: Optional[str] = Field(None, max_length=50)
    practice_id: Optional[uuid.UUID] = None
    send_invitation: bool = True
    skip_existing: bool = True
    frontend_test_base_url: Optional[str] = None

class AdminUserCreatedOut(BaseModel):
    id: uuid.UUID
    username: str
    password: Optional[str] = None
    email: Optional[EmailStr] = None
    group_name: Optional[str] = None
    assigned_practice_id: Optional[uuid.UUID] = None
    invitation_sent: bool = False
    invitation_error: Optional[str] = None
    already_existed: bool = False

class AdminBulkUserCreateResponse(BaseModel):
    created: List[AdminUserCreatedOut]
    existing: List[AdminUserCreatedOut]
    failed: List[dict] = Field(default_factory=list)
    created_count: int
    existing_count: int
    failed_count: int

class AdminUserSearchResponse(BaseModel):
    items: List[AdminUserOut]
    total: int
    offset: int
    limit: int

class AdminVacancyOut(BaseORMModel):
    id: uuid.UUID
    job_name: str
    job_description: str
    tag: str
    start_date: date
    end_date: date
    company_id: Optional[uuid.UUID] = None
    company_name: Optional[str] = None
    candidate_count: Optional[int] = 0
    is_available: Optional[bool] = True

class AdminVacancyCreate(BaseModel):
    job_name: str = Field(..., max_length=100)
    job_description: str
    tag: str
    start_date: date
    end_date: date
    company_id: Optional[uuid.UUID] = None
    is_available: bool = True

class AdminVacancyUpdate(BaseModel):
    job_name: Optional[str] = Field(None, max_length=100)
    job_description: Optional[str] = None
    tag: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    company_id: Optional[uuid.UUID] = None
    is_available: Optional[bool] = None

class AdminCandidateOut(BaseORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: Optional[str] = None
    user_username: Optional[str] = None
    vacancy_id: Optional[uuid.UUID] = None
    position_title: Optional[str] = None
    company_name: Optional[str] = None
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
    question_texts: List[str] = []
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
    practice_title: Optional[str] = None
    user_id: uuid.UUID
    user_name: Optional[str] = None
    user_username: Optional[str] = None
    assigned_at: datetime
    is_completed: bool
    completed_at: Optional[datetime] = None

class PracticeAssignmentResult(BaseModel):
    added: int
    removed: int
    skipped_existing: int
    invitation_sent: int
    invitation_failed: int
    invitation_errors: List[str] = Field(default_factory=list)

class PracticeInvitationRequest(BaseModel):
    user_ids: List[uuid.UUID] = Field(default_factory=list)
    groups: List[str] = Field(default_factory=list)
    include_completed: bool = False
    frontend_test_base_url: Optional[str] = None
    invitation_message: Optional[str] = None

class PracticeInvitationResult(BaseModel):
    targeted: int
    sent: int
    failed: int
    errors: List[str] = Field(default_factory=list)

class AdminTestSessionOut(BaseORMModel):
    session_id: uuid.UUID
    practice_id: uuid.UUID
    practice_title: Optional[str] = None
    user_id: uuid.UUID
    user_name: Optional[str] = None
    user_username: Optional[str] = None
    overall_points: float
    is_finished: bool
    started_time: datetime

class AdminUserAnswerOut(BaseORMModel):
    id: uuid.UUID
    session_id: Optional[uuid.UUID] = None
    question_id: Optional[uuid.UUID] = None
    question_text: Optional[str] = None
    user_answer: Optional[str] = None
    user_answer_text: Optional[str] = None
    correct_answer_text: Optional[str] = None
    is_correct: Optional[bool] = None
    points_awarded: Optional[float] = None
    time_spent: Optional[float] = None
