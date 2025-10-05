from fastapi import  APIRouter, Depends, HTTPException
from schemas.user_schema import UserCreate, UserResponse
from database.database import SessionLocal, engine
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from database.models import User
from auth.jwt_handler import create_access_token, verify_access_token
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")



router = APIRouter(prefix="/users")


def get_data():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


SECRET_KEY = "123012o30120mewkfmwfewi"
def get_current_user(db: Session = Depends(get_data), token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user



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
