from fastapi import APIRouter, Depends, Query
from database.database import get_db
from schemas.user_schema import UserProfileOut
from sqlalchemy.orm import Session
from database.models import User, TestSession
from routers.login import get_current_user

router = APIRouter(prefix="/users/me", tags=["User Profile"])


@router.get("", response_model=UserProfileOut)
def get_user_profile(user: User = Depends(get_current_user)):
    # `get_current_user` already loaded the user from the DB. Reusing that
    # object avoids an unnecessary second SELECT on every profile fetch.
    return UserProfileOut(
        name=user.name,
        surname=user.surname,
        username=user.username,
        age=user.age,
        email=user.email,
    )


@router.get("/activity")
def get_user_activity(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Cap & order the result set in SQL — the unbounded `.all()` used to
    # return *every* TestSession for the user, which scales badly.
    activities = (
        db.query(
            TestSession.started_time,
            TestSession.overall_points,
            TestSession.is_finished,
        )
        .filter(TestSession.user_id == user.id)
        .order_by(TestSession.started_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "startDate": started_time,
            "overalPoints": overall_points,
            "isFinished": is_finished,
            "reportsUrl": "url",
        }
        for started_time, overall_points, is_finished in activities
    ]
