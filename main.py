from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import User
from routers import (
    admin_panel,
    candidate_dashboard,
    email,
    login,
    main_page,
    questions,
    tester_main,
    user_profile,
)

app = FastAPI(title="HR Assistant API", version="1.0.0")

# API routers are grouped by domain. Each router owns its /api/v1 prefix.
app.include_router(login.router)
app.include_router(email.router)
app.include_router(user_profile.router)
app.include_router(main_page.router)
app.include_router(candidate_dashboard.router)
app.include_router(admin_panel.router)
app.include_router(questions.router)
app.include_router(tester_main.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://hr-assistant-j2u1.vercel.app",
        "https://ai-talent-flow.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_data():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/api/v1/users", tags=["Users"])
def list_users(db: Session = Depends(get_data)):
    return db.query(User).all()

@app.get("/api/v1/health/ping", tags=["Health"])
def ping():
    return {"message": "pong"}
