from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from database.database import SessionLocal, engine
from database.models import User
from routers import login

app = FastAPI()

app.include_router(login.router, prefix= "/auth", tags= ["authentication"])


def get_data():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/test/")
async def test(db: Session = Depends(get_data)):
    users = db.query(User).all()
    return users