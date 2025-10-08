import os
import shutil
import uuid
from fastapi import APIRouter, HTTPException, UploadFile
from hrassistant.database.database import SessionLocal
from routers.login import get_data, get_current_user
from schemas.user_schema import VacancyResponse
from database.models import Created_Vacancy, User, Company
from fastapi import Depends
from sqlalchemy.orm import Session
from PyPDF2 import PdfReader
router = APIRouter()

### api for creating vacancies rn works only taking ids from frontend

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


### api for listing all the vacancies

@router.get("/vacancies", response_model=list[VacancyResponse])
async def get_vacancies(db: Session = Depends(get_data), current_user: User = Depends(get_current_user)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=400, detail="Company not found for this user")
    vacancies = db.query(Created_Vacancy).filter(Created_Vacancy.company_id == company.id).all()
    return vacancies


@router.post("/vacancies/upload_resumes")
async def upload_resumes(file: UploadFile = File(...)):
    db: Session = SessionLocal()
    file_count = 1
    UPLOAD_DIR = ""


    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)


    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    for i in range(file_count):
        if i.endswith("pdf"):
            reader = PdfReader(file_path)
            text_content = " ".join([page.extract_text() or "" for page in reader.pages])
        else:
            return("Invalid Content")
