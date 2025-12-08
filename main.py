from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from database.database import SessionLocal, engine
from database.models import User
from routers import email, login, main_page, questions, tester_main 
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.include_router(login.router, prefix= "", tags= ["authentication"])
app.include_router(main_page.router, prefix= "", tags= ["create_job"])
app.include_router(email.router, prefix= "", tags= ["email"])
app.include_router(main_page.router, prefix= "", tags= ["vacancies"])
app.include_router(tester_main.router, prefix= "", tags= ["my-tests"])
app.include_router(questions.router, prefix= "", tags= ["tests"])

origins = [
    "http://localhost:3000",   # frontend dev URL
    "https://localhost:5173",  # production URL
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,          # List of allowed origins
    allow_credentials=True,         # Allow cookies, authorization headers
    allow_methods=["*"],            # Allow all HTTP methods
    allow_headers=["*"],            # Allow all headers
)
def get_data():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/users")
async def test(db: Session = Depends(get_data)):
    users = db.query(User).all()
    return users


@app.get("/ping")
async def ping():
    return {"message": "pong"}

