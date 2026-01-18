from datetime import date
from typing import Optional
import uuid
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
    role : Role

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

class TestStatusResponse(BaseModel):
    message: str
    is_correct: bool
    correct_answer: Optional[str] = None
    points_awarded: float
    is_test_finished: bool