import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database.database import Base, engine
from database.database import SessionLocal
# Assuming your models are correctly defined in database.models/database
from database.models import * 
from database import models
import json


# NOTE ON SCHEMA CHANGES: Base.metadata.create_all() only creates tables
# that do not exist. If you change a model (like adding the 'owner' column
# to StartedTest), you must manually delete your old database file (e.g., 'test.db')
# and run this script again to apply the new schema.
Base.metadata.create_all(bind=engine)

# Create tables in the database
def seed_questions():
    db: Session = SessionLocal()

    questions = [
        # --- MATH (easy 1-3) ---
        ("math", "2 + 2 = ?", "4", ["3", "4", "5", "6"], 1, 1.1),
        ("math", "5 - 3 = ?", "2", ["1", "2", "3", "4"], 1, 1.1),
        ("math", "10 / 2 = ?", "5", ["4", "5", "6", "8"], 2, 1.2),
        ("math", "3 * 4 = ?", "12", ["9", "10", "12", "14"], 2, 1.2),
        ("math", "√81 = ?", "9", ["7", "8", "9", "10"], 3, 1.3),
        ("math", "12 * 8 = ?", "96", ["84", "96", "108", "120"], 4, 1.4),
        ("math", "log2(64) = ?", "6", ["4", "5", "6", "7"], 5, 1.5),
        ("math", "sin(90°) = ?", "1", ["0", "1", "0.5", "-1"], 6, 1.6),
        ("math", "15² = ?", "225", ["200", "215", "225", "250"], 7, 1.7),
        ("math", "√625 = ?", "25", ["20", "25", "30", "35"], 7, 1.7),
        ("math", "8³ = ?", "512", ["256", "512", "128", "1024"], 8, 1.8),
        ("math", "cos(0°) = ?", "1", ["0", "1", "-1", "0.5"], 9, 1.9),

        # --- PYTHON (easy to hard 1-9) ---
        ("python", "What is the output of print(2 + 3 * 4)?", "14", ["20", "14", "24", "12"], 1, 1.1),
        ("python", "Which keyword defines a function in Python?", "def", ["func", "function", "def", "lambda"], 2, 1.2),
        ("python", "What is the output of len('ChatGPT')?", "7", ["6", "7", "8", "5"], 3, 1.3),
        ("python", "Which collection is ordered and immutable?", "tuple", ["list", "set", "tuple", "dict"], 4, 1.4),
        ("python", "What does the 'self' keyword refer to in a class?", "the instance", ["the class", "a module", "the instance", "None"], 5, 1.5),
        ("python", "What is the output of 3 == 3.0 in Python?", "True", ["True", "False", "Error", "None"], 6, 1.6),
        ("python", "Which decorator is used for static methods?", "@staticmethod", ["@classmethod", "@staticmethod", "@property", "@static"], 7, 1.7),
        ("python", "What will print(type(lambda x: x)) show?", "<class 'function'>", ["<class 'lambda'>", "<class 'func'>", "<class 'function'>", "<lambda>"], 8, 1.8),
        ("python", "What’s the output of [i for i in range(3)]?", "[0, 1, 2]", ["[1,2,3]", "[0,1,2]", "(0,1,2)", "{0,1,2}"], 9, 1.9)
    ]

    for q in questions:
        user_question = models.Question(
            category=q[0],
            text=q[1],
            correct_answer=q[2],
            options=json.dumps(q[3]), # JSON.dumps() is needed for the JSON column
            difficulty_level=q[4],
            points=q[5]
        )
        db.add(user_question)

    db.commit()
    db.close()
    print("✅ Questions added successfully!")


def insert_test_data(db: Session):
    """
    Inserts necessary test data (Company, User, Questions, and two StartedTest records) 
    into the given SQLAlchemy session.
    """

    print("--- Inserting Test Data ---")
    
    # --- 1. Create Company ---
    company1 = Company(
        name="TechTest Corp",
        email="hr@techtest.com",
        INN="9876543210",
        phone_number="555-9000"
    )
    db.add(company1)
    db.commit()
    db.refresh(company1)
    print(f"1. Created Company: {company1.name} (ID: {company1.id})")

    # --- 2. Create User ---
    user1 = User(
        username="user",
        role="Candidate",
        password="1234", # Should be hashed in production
    )
    db.add(user1)
    db.commit()
    db.refresh(user1)
    print(f"2. Created User: {user1.username} (ID: {user1.id})")

    # --- 3. Create User Profile ---
    profile1 = UserProfile(
        userid=user1.id,
        name="Alex",
        surname="Smith",
        age=28
    )
    db.add(profile1)
    print("3. Created UserProfile.")

    # --- 4. Create Questions ---
    # Fetch questions needed for foreign key constraint in UserAnswer
    q_python = db.query(Question).filter(Question.category == 'python').first()
    q_math = db.query(Question).filter(Question.category == 'math').first()
    print(f"4. Re-fetched sample questions for FKs.")
    
    # --- 5. Create StartedTest records ---

    # A. Active/In-progress Test (for /active_test)
    active_test = StartedTest(
        user_id=user1.id,
        owner=company1.id,
        deadline=datetime.now() + timedelta(days=5),
        current_level=2,
        current_score=5.5,
        is_active=True
    )
    db.add(active_test)
    
    # B. Passive/Completed Test (for /test_history)
    completed_test = StartedTest(
        user_id=user1.id,
        owner=company1.id,
        deadline=datetime.now() - timedelta(days=10), # Expired/Completed
        created_at=datetime.now() - timedelta(weeks=4),
        current_level=9, # Finished all levels
        current_score=98.0, 
        is_active=False
    )
    db.add(completed_test)
    db.commit()
    print("5. Created 1 Active Test and 1 Completed Test.")

    # --- 6. Create a sample UserAnswer for the completed test ---
    if q_python:
        answer = UserAnswer(
            user_id=user1.id,
            question_id=q_python.id,
            user_answer="str",
            is_correct=True,
            score_awarded=q_python.points
        )
        db.add(answer)
        db.commit()
        print("6. Added sample UserAnswer for the completed test.")
        
    print("--- Test Data Insertion Complete ---")

if __name__ == "__main__":
    # Ensure tables are created before inserting data
    Base.metadata.create_all(bind=engine) 

    # Seed the generic questions
    seed_questions() 

    # Seed the company, user, test, and answer data
    db = SessionLocal()
    try:
        insert_test_data(db)
    finally:
        db.close()