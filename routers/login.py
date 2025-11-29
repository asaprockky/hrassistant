from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from database.database import SessionLocal, get_db
from database.models import StartedTest, User
from auth.jwt_handler import create_access_token
from passlib.context import CryptContext

from schemas.user_schema import UserCreate

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

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # Prepare the exception - we use this in multiple places below
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 1. Decode the token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # 2. Extract the user ID (matches what you put in the token during login)
        user_id: int = payload.get("user_id")
        
        if user_id is None:
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception

    # 3. Fetch the user from the DB
    user = db.query(User).filter(User.id == user_id).first()
    
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

    return {"access_token": access_token}



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
        password = hashed_pwd
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    access_token = create_access_token(
        data={"user_id": new_user.id, "username": new_user.username}
    )
    response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,   # Essential security feature
            secure=False,    # Change to True if using HTTPS
            samesite="lax",
            max_age=3600
        )

    # E. Return the token in the response body (Standard for API consumption)
    return {"access_token": access_token}

