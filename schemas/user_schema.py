from datetime import date
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str
    password: str


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


class AnswerCreate(BaseModel):
    """
    Schema for the data sent by the user to submit an answer.
    All fields are REQUIRED (indicated by '...').
    """
    question_id: int = Field(
        ..., 
        description="The ID of the question being answered."
    )
    answer: str = Field(
        ..., 
        description="The user's submitted answer text/value."
    )
    correct: bool = Field(
        ..., 
        description="Indicates if the user's answer was correct (True) or incorrect (False)."
    )
# schema for returning answer info
class AnswerResponse(BaseModel):
    question_id: int
    answer_text: str
    points_awarded: float
    total_score: float
    level: int
    difficulty: str

    class Config:
        orm_mode = True
