from datetime import date
from pydantic import BaseModel


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




class Answer(BaseModel):
    correct: bool