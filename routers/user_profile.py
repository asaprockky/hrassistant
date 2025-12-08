from datetime import datetime
from http.client import HTTPException
from fastapi import APIRouter, Depends
from database.database import get_db
from schemas.user_schema import UserProfileOut
from sqlalchemy.orm import Session
from database.models import User, StartedTest
from routers.login import get_current_user
router = APIRouter()



@router.get("/users/me", response_model=UserProfileOut)
def user_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_data = db.query(User).filter(User.id == user.id).first()
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    print(f"We Got the data {user_data}")
    return UserProfileOut(
        name=user_data.name,
        surname=user_data.surname,
        username = user_data.username,
        age=user_data.age,
        email=user_data.email
    )

