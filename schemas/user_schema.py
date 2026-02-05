from datetime import date, datetime

from typing import List, Optional
import uuid

from sqlalchemy import UUID
from database.enums import Role
from pydantic import BaseModel, Field, EmailStr




class CompanyOut(BaseModel):
    id: int
    name: str
    phone_number: Optional[str]
    INN: Optional[str]
    email: Optional[EmailStr]

    class Config:
        # Renamed to from_attributes in Pydantic v2
        orm_mode = True 

class UserProfileOut(BaseModel):
    # Assuming UserProfile SQLAlchemy model has these fields
    name: str
    surname: str
    username : str
    age: int
    email: Optional[EmailStr]


    class Config:
        orm_mode = True

class UserProfilePageOut(BaseModel):
    id: int
    username: str
    role: str
    company: Optional[CompanyOut] # Pydantic model for the related Company data
    profile: Optional[UserProfileOut] # Pydantic model for the related Profile data

    class Config:
        orm_mode = True



        
class UserCreate(BaseModel):
    username: str
    password: str
    role: Role
    # Added required profile fields
    name: str
    surname: str
    age: int
    email: str | None = None



class EmailUpdate(BaseModel):
    email : str
class UserResponse(BaseModel):
    id: int
    username: str

    class Config:
        orm_mode = True




class VacancyResponse(BaseModel):
    id: int
    job_name: str
    job_description: str
    tag: str
    start_date: date
    end_date: date
    company_id: int

    class Config:
        orm_mode = True  # allows SQLAlchemy models to be converted to JSON

# --- Pydantic Models ---
class AnswerCreate(BaseModel):
    question_id: uuid.UUID
    user_answer: str  # This receives the Option ID (UUID string)
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
    question_ids: List[uuid.UUID]  # The IDs selected by the creator
    tags: List[str] = [] 

class AssignmentUpdate(BaseModel):
    add_user_ids: List[uuid.UUID] = []     # Users to assign
    remove_user_ids: List[uuid.UUID] = []  # Users to de-assign

class AssignmentListResponse(BaseModel):
    assignment_id: UUID
    practice_title: str
    user_full_name: str
    is_completed: bool
    assigned_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True