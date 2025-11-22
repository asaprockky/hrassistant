from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from database.database import SessionLocal, engine
from database.models import User
from routers import login, main_page, questions

app = FastAPI()

app.include_router(login.router, prefix= "", tags= ["authentication"])
app.include_router(main_page.router, prefix= "", tags= ["create_job"])
app.include_router(main_page.router, prefix= "", tags= ["vacancies"])
app.include_router(questions.router, prefix= "", tags= ["tests"])


def get_data():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/users")
async def test(db: Session = Depends(get_data)):
    users = db.query(User).all()
    return {"message": "hello"}


@app.get("/ping")
async def ping():
    return {"message": "pong"}

