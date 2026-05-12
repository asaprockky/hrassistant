import os
import shutil
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File
from routers.login import get_data, get_current_user
from schemas.user_schema import VacancyResponse
from database.models import Created_Vacancy, User, Company
from fastapi import Depends
from sqlalchemy.orm import Session
from PyPDF2 import PdfReader
router = APIRouter(prefix="/vacancies", tags=["Vacancies"])


@router.post("", response_model=VacancyResponse)
def create_vacancy(data: VacancyResponse, db: Session = Depends(get_data), current_user: User = Depends(get_current_user)):
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



@router.get("", response_model=list[VacancyResponse])
def list_vacancies(db: Session = Depends(get_data), current_user: User = Depends(get_current_user)):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=400, detail="Company not found for this user")
    vacancies = db.query(Created_Vacancy).filter(Created_Vacancy.company_id == company.id).all()
    return vacancies

    
@router.post("/resume-uploads")
def upload_resume(file: UploadFile = File(...)):
    UPLOAD_DIR = ''
    try:
        unique_filename = f"{uuid.uuid4()}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)


        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)


        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Invalid file type. Only PDFs are allowed.")

        reader = PdfReader(file_path)
        text_content = " ".join([page.extract_text() or "" for page in reader.pages])

        return {
            "message": "Resume uploaded and processed successfully",
            "filename": unique_filename,
            "content_preview": text_content[:500]  
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")

