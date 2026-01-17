import datetime
from email.message import EmailMessage
import random
import smtplib
import ssl
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import enums, models
from database.database import SessionLocal, get_db
from database.models import User
from auth.jwt_handler import create_access_token
from passlib.context import CryptContext
import uuid

from schemas.user_schema import UserCreate, EmailUpdate

router = APIRouter(prefix="/users")

SECRET_KEY = "supersecretkey123"
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password,hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_data():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
def get_current_user(request: Request, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 1. Check the Cookie Header (What the browser sends)
    token = request.cookies.get("access_token")
    
    # 2. Check the Authorization Header (What Swagger/API clients send)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        # If no token found in either location, we raise the exception
        raise credentials_exception

    try:
        # 3. Decode the token (Verifies signature and expiration)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # 4. Extract the user ID (String format)
        user_id_str: str = payload.get("user_id") # Renamed for clarity 
        
        if user_id_str is None:
            raise credentials_exception
            
        # 🟢 CRITICAL STEP ADDED 🟢
        # Convert the string from the token into a Python UUID object
        try:
            user_id_uuid = uuid.UUID(user_id_str)
        except ValueError:
            # Handle case where the string isn't a valid UUID format
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format in token")
            
    except JWTError:
        # Handle expired or tampered tokens
        raise credentials_exception

    # 5. Fetch the user from the DB using the UUID object
    # This comparison now works: UUID Column == Python UUID Object
    user = db.query(User).filter(User.id == user_id_uuid).first() 
    
    if user is None:
        raise credentials_exception
        
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
        data={"user_id": str(user.id), "username": user.username}
    )
    user_role = user.role
    # set JWT cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=604800,
    )

    return {"access_token": access_token, "user_role" : user_role}



@router.post("/signup")
def signup(user_data: UserCreate, response: Response,  db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code= status.HTTP_409_CONFLICT, 
            detail = "Username Already Taken"
        )
    hashed_pwd = get_password_hash(user_data.password)
    new_user = User(
        username = user_data.username,
        role= user_data.role,
        password = hashed_pwd
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    access_token = create_access_token(
        data={"user_id": str(new_user.id), "username": new_user.username}
    )
    response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,   
            secure=False,  
            samesite="lax",
            max_age=604800
        )
    return {"access_token": access_token}

