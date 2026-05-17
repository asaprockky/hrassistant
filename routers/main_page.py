import os
import shutil
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from database.database import SessionLocal
from routers.login import get_data, get_current_user
from schemas.user_schema import VacancyResponse
from database.models import Created_Vacancy, User, Company
from fastapi import Depends
from sqlalchemy.orm import Session
from PyPDF2 import PdfReader
router = APIRouter(prefix="/vacancies", tags=["Vacancies"])


@router.post("", response_model=VacancyResponse)
async def create_vacancy(data: VacancyResponse, db: Session = Depends(get_data), current_user: User = Depends(get_current_user)):
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Company not found for this user")
    # We already know the company_id from the authenticated user — skip the
    # extra SELECT against `companies` that was happening on every create.
    new_vacancy = Created_Vacancy(
        job_name=data.job_name,
        job_description=data.job_description,
        tag = data.tag,
        start_date=data.start_date,
        end_date=data.end_date,
        company_id=current_user.company_id
    )

    db.add(new_vacancy)
    db.commit()
    db.refresh(new_vacancy)
    return new_vacancy



@router.get("", response_model=list[VacancyResponse])
async def list_vacancies(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_data),
    current_user: User = Depends(get_current_user),
):
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Company not found for this user")
    # Bound the page size and skip the redundant company lookup — the
    # foreign key already lives on `current_user`.
    return (
        db.query(Created_Vacancy)
        .filter(Created_Vacancy.company_id == current_user.company_id)
        .order_by(Created_Vacancy.start_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    
@router.post("/resume-uploads")
async def upload_resume(file: UploadFile = File(...)):
    UPLOAD_DIR = ''
    db: Session = SessionLocal()
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

    finally:
        db.close()



