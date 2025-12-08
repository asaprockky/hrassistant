import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import text  # Required for raw SQL execution
from sqlalchemy.sql import func

# Ensure these imports match your project structure
# If specific models are missing from this list, ensure they are imported here
from database.database import engine, SessionLocal, Base
from database.enums import Role
from database.models import (
    Company, User, Created_Vacancy, Candidate, 
    Question, UserAnswer, StartedTest
)

# --- Define the data to be inserted ---

# 1. Company
company_id_1 = uuid.uuid4()
COMPANY_DATA = Company(
    id=company_id_1,
    name="TechCorp Solutions",
    phone_number="555-0101",
    INN="1234567890",
    email="admin@techcorp.com"
)

# 2. Users
user_id_1 = uuid.uuid4() # Admin/Recruiter
user_id_2 = uuid.uuid4() # Standard User/Candidate

USER_DATA = [
    User(
        id=user_id_1,
        username="admin",
        role=Role.ADMIN,
        # NOTE: In a real app, hash this password!
        password="1234", 
        company_id=company_id_1,
        name="Alice",
        surname="Smith",
        age=35,
        email="alice.smith@techcorp.com"
    ),
    User(
        id=user_id_2,
        username="user",
        role=Role.USER,
        password="1234",
        # company_id is None for a standard candidate user
        name="Bob",
        surname="Johnson",
        age=28,
        email="bob.johnson@example.com"
    ),
]

# 3. Vacancy (Created by the Company)
vacancy_id_1 = uuid.uuid4()
VACANCY_DATA = Created_Vacancy(
    id=vacancy_id_1,
    job_name="Senior Python Developer",
    job_description="Develop and maintain high-performance backend services.",
    tag="Python, FastAPI, PostgreSQL",
    start_date=datetime.now().date(),
    end_date=(datetime.now() + timedelta(days=60)).date(),
    company_id=company_id_1
)

# 4. Candidate (Applying to the Vacancy)
candidate_id_1 = uuid.uuid4()
CANDIDATE_DATA = Candidate(
    id=candidate_id_1,
    full_name="Bob Johnson",
    resume_loc="/resumes/bob_resume.pdf",
    ai_score=0.78,
    education="M.S. Computer Science",
    experience="5 years",
    skills="Python, SQL, AWS",
    vacancy_id=vacancy_id_1
)

# 5. Question and Test Data
question_id_1 = uuid.uuid4()
question_id_2 = uuid.uuid4()

QUESTION_DATA = [
    Question(
        id=question_id_1,
        text="What is a closure in Python?",
        difficulty_level=5,
        correct_answer="A function having access to the scope of its enclosing function.",
        options={'a': 'A function having access to the scope of its enclosing function.', 
                 'b': 'A type of decorator.', 
                 'c': 'A built-in data structure.'},
        category="Python",
        points=10.0
    ),
    Question(
        id=question_id_2,
        text="Which SQL command is used to retrieve data?",
        difficulty_level=2,
        correct_answer="SELECT",
        options={'a': 'RETRIEVE', 'b': 'GET', 'c': 'SELECT'},
        category="SQL",
        points=5.0
    )
]

# 6. User Test/Answer Data (Bob starts a test, answers Q1 correctly, Q2 incorrectly)
test_id_1 = uuid.uuid4()

STARTED_TEST_DATA = StartedTest(
    test_id=test_id_1,
    user_id=user_id_2, # Bob Johnson
    owner=company_id_1, # TechCorp Solutions
    # Fixed: Used datetime.now(timezone.utc) to avoid DeprecationWarning
    deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    current_level=2,
    current_score=10.0,
    is_active=True
)

USER_ANSWER_DATA = [
    UserAnswer(
        user_id=user_id_2,
        question_id=question_id_1,
        user_answer="A function having access to the scope of its enclosing function.",
        is_correct=True,
        score_awarded=10.0
    ),
    UserAnswer(
        user_id=user_id_2,
        question_id=question_id_2,
        user_answer="RETRIEVE",
        is_correct=False,
        score_awarded=0.0
    )
]


# --- Seeding Function ---

def seed_database():
    """Drops tables, recreates them, and inserts dummy data."""
    print("Resetting database (Dropping and Creating Tables)...")
    
    # 1. FORCE CLEANUP: Manually drop the conflicting table using raw SQL
    # This fixes the 'DependentObjectsStillExist' error.
    with engine.connect() as connection:
        connection.execute(text("DROP TABLE IF EXISTS user_profile CASCADE"))
        connection.commit()

    # 2. Standard SQLAlchemy Drop/Create
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Database reset complete.")
    
    # Start the session
    db = SessionLocal()
    
    try:
        print("Inserting fake data...")
        
        # Insert Company
        db.add(COMPANY_DATA)
        
        # Insert Users
        db.add_all(USER_DATA)
        
        # Insert Vacancy
        db.add(VACANCY_DATA)
        
        # Insert Candidate
        db.add(CANDIDATE_DATA)
        
        # Insert Questions
        db.add_all(QUESTION_DATA)
        
        # Insert Started Test
        db.add(STARTED_TEST_DATA)
        
        # Insert User Answers
        db.add_all(USER_ANSWER_DATA)
        
        db.commit()
        print("✅ Data seeding complete!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error during seeding: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()