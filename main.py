from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends, Query
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

API_TAGS = [
    {"name": "Health"},
    {"name": "Authentication"},
    {"name": "Users"},
    {"name": "User Profile"},
    {"name": "Email Verification"},
    {"name": "Vacancies"},
    {"name": "Candidate Dashboard"},
    {"name": "Admin"},
    {"name": "Testing"},
    {"name": "Test Sessions"},
    {"name": "Resumes"},
]

app = FastAPI(title="HR Assistant API", version="1.0.0", openapi_tags=API_TAGS)

app.include_router(login.router)
app.include_router(user_profile.router)
app.include_router(email.router)
app.include_router(main_page.router)
app.include_router(candidate_dashboard.router)
app.include_router(admin_panel.router)
app.include_router(questions.router)
app.include_router(tester_main.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://admin-talent-flow.vercel.app",
        "http://localhost:5174",
        "http://localhost:5175",
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

@app.get("/users", tags=["Users"])
def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_data),
):
    # Previously returned every User row in the system — fine with 10 rows,
    # painful with thousands. Default page is bounded.
    return (
        db.query(User)
        .order_by(User.surname.asc(), User.name.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

@app.get("/health/ping", tags=["Health"])
def ping():
    return {"message": "pong"}
