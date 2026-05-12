from fastapi import APIRouter, Depends
from database.database import get_db
from schemas.user_schema import UserProfileOut
from sqlalchemy.orm import Session
from database.models import User, TestSession
from routers.login import get_current_user
router = APIRouter(prefix="/users/me", tags=["User Profile"])



@router.get("", response_model=UserProfileOut)
def get_user_profile(user: User = Depends(get_current_user)):
    return UserProfileOut(
        name=user.name,
        surname=user.surname,
        username=user.username,
        age=user.age,
        email=user.email
    )

@router.get("/activity")
def get_user_activity(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    activities = (
        db.query(TestSession)
        .filter(TestSession.user_id == user.id)
        .all()
    )

    return [
        {
            "startDate": a.started_time,
            "overalPoints": a.overall_points,
            'isFinished': a.is_finished,
            "reportsUrl": 'url'
        }
        for a in activities
    ]
