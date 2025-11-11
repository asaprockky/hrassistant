from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from database.database import SessionLocal
from database.models import User
from auth.jwt_handler import create_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")

router = APIRouter(prefix="/users")

SECRET_KEY = "supersecretkey123"


def get_data():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(db: Session = Depends(get_data), token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/login")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_data)
):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or user.password != form_data.password:
        raise HTTPException(status_code=400, detail="Invalid username or password")

    access_token = create_access_token(
        data={"user_id": user.id, "username": user.username}
    )

    # set JWT cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=3600,
    )

    return {"access_token": access_token, "token_type": "bearer"}
