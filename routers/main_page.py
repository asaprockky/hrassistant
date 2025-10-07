from fastapi import APIRouter, HTTPException
from routers.login import get_data, get_current_user
from schemas.user_schema import VacancyResponse
from database.models import Created_Vacancy, User, Company
from fastapi import Depends
from sqlalchemy.orm import Session
router = APIRouter()



@router.post("/vacancies/create", response_model= VacancyResponse)
async def crete_vacancy(data: VacancyResponse, db: Session = Depends(get_data), current_user: User = Depends(get_current_user)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=400, detail="Company not found for this user")
    new_vacancy = Created_Vacancy(
        job_name=data.job_name,
        job_description=data.job_description,
        tag = data.tag,
        start_date=data.start_date,
        end_date=data.end_date,
        company_id=company.id
    )

    db.add(new_vacancy)
    db.commit()
    db.refresh(new_vacancy)
    return new_vacancy