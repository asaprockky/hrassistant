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
from auth.jwt_handler import create_access_token, create_refresh_token, verify_access_token
from passlib.context import CryptContext
import uuid
from database.models import Role
from pydantic import BaseModel, Field
from schemas.user_schema import UserCreate, EmailUpdate, PublicRegister
from auth.jwt_handler import SECRET_KEY, ALGORITHM


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: Optional[str] = None
    new_password: str = Field(..., min_length=4)

router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password):
    # Bcrypt fails if input is > 72 bytes, so we truncate
    password = password.encode("utf-8")[:72]
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    # Must match the hashing logic
    plain_password = plain_password.encode("utf-8")[:72]
    return pwd_context.verify(plain_password, hashed_password)

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

    user = db.query(User).filter(User.id == user_id_uuid).first() 
    
    if user is None:
        raise credentials_exception
    
    return user

def get_current_user_from_token(token: str, db: Session) -> Optional[User]:
    """Decodes a JWT and returns the User, or None if invalid."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("user_id")
        
        if not user_id_str:
            return None
            
        user_id_uuid = uuid.UUID(user_id_str)
        return db.query(User).filter(User.id == user_id_uuid).first()
        
    except (JWTError, ValueError):
        # Catches expired tokens, bad signatures, and invalid UUID strings
        return None

def get_current_admin(current_user = Depends(get_current_user)):
    # Adjust "Role.ADMIN" to match exactly how you defined it in your Enum
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not authorized. Admin access required."
        )
    return current_user

# Remove 'async' to fix performance blocking

@router.post("/login")
def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_data)
):
    # 1. Fetch User
    user = db.query(User).filter(User.username == form_data.username).first()

    # 2. Verify Password Correctly
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid username or password")

    # 3. Create Tokens (short-lived access + long-lived refresh — see U1)
    token_payload = {"user_id": str(user.id), "username": user.username}
    access_token = create_access_token(data=token_payload)
    refresh_token = create_refresh_token(data=token_payload)

    # 4. Set Cookie (Best effort for browsers)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False, # Set to True if using HTTPS
        samesite="lax",
        max_age=6048000,
    )

    # 5. Return Token AND User Profile Data
    # Best practice is to group the profile data inside a "user" dictionary
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        # U2: tells the client to force a password-change screen before any
        # other page when the account was admin-created/invited/reset.
        "must_change_password": bool(user.must_change_password),
        "user": {
            "id": str(user.id),
            "name": user.name,
            "surname": user.surname,
            "username": user.username,
            "userRole": str(user.role.value if hasattr(user.role, "value") else user.role),
            "age": user.age,
            "email": user.email,
            "group_name": user.group_name,
            "must_change_password": bool(user.must_change_password),
        }
    }



@router.post("/register")
def register_user(user_data: PublicRegister, response: Response, db: Session = Depends(get_db)):
    """Public self sign-up (U3).

    Security: the role and company are NEVER taken from the request body — a
    self-registered account is always a plain USER with no company. This
    closes the previous privilege-escalation hole where clients could send
    `role=ADMIN`.
    """
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username Already Taken"
        )
    if user_data.email:
        existing_email = db.query(User).filter(User.email == str(user_data.email)).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered"
            )

    hashed_pwd = get_password_hash(user_data.password)

    new_user = User(
        username=user_data.username,
        role=Role.USER,            # forced — never trust client-supplied role
        company_id=None,           # self-registered users belong to no company
        password=hashed_pwd,
        name=user_data.name or user_data.username,
        surname=user_data.surname or "",
        age=user_data.age if user_data.age is not None else 0,
        email=str(user_data.email) if user_data.email else None,
        must_change_password=False,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token_payload = {"user_id": str(new_user.id), "username": new_user.username}
    access_token = create_access_token(data=token_payload)
    refresh_token = create_refresh_token(data=token_payload)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=604800
    )

    # The client gates the user into "complete your profile" when these are
    # missing (U3).
    profile_complete = bool(new_user.name and new_user.surname and new_user.age)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "must_change_password": False,
        "profile_complete": profile_complete,
        "user": {
            "id": str(new_user.id),
            "name": new_user.name,
            "surname": new_user.surname,
            "username": new_user.username,
            "userRole": str(new_user.role.value if hasattr(new_user.role, "value") else new_user.role),
            "age": new_user.age,
            "email": new_user.email,
            "group_name": new_user.group_name,
            "must_change_password": False,
        },
    }


@router.post("/refresh")
def refresh_access_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access token (U1)."""
    decoded = verify_access_token(payload.refresh_token)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = db.query(User).filter(User.id == decoded.get("user_id")).first()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")

    token_payload = {"user_id": str(user.id), "username": user.username}
    return {
        "access_token": create_access_token(data=token_payload),
        "refresh_token": create_refresh_token(data=token_payload),
    }


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set a new password and clear the must_change_password flag (U2).

    `current_password` is required for normal voluntary changes; it is
    optional for the forced first-login change (the user was just issued a
    temporary password by an admin).
    """
    if not current_user.must_change_password:
        if not payload.current_password or not verify_password(
            payload.current_password, current_user.password
        ):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password = get_password_hash(payload.new_password)
    current_user.must_change_password = False
    db.commit()
    return {"ok": True, "must_change_password": False}
