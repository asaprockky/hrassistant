from fastapi import  APIRouter, Depends, HTTPException
from schemas.user_schema import UserCreate, UserResponse
from database.database import SessionLocal, engine
from sqlalchemy.orm import Session
from database.models import User
from auth.jwt_handler import create_access_token, verify_access_token


router = APIRouter()


def get_data():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/login")
async def login(user_data: UserCreate, db: Session = Depends(get_data)):
    user = db.query(User).filter(User.username == user_data.username).first()
    
    if not user or user.password != user_data.password:
        raise HTTPException(status_code=400, detail="Invalid username or password")

    access_token = create_access_token(data={"user_id": user.id, "username": user.username})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_role": user.role
    }
