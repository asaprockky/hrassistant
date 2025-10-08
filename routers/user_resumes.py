from fastapi import APIRouter, HTTPException
from routers.login import get_data, get_current_user
from schemas.user_schema import VacancyResponse
from database.models import Created_Vacancy, User, Company
from fastapi import Depends
from sqlalchemy.orm import Session
router = APIRouter()

