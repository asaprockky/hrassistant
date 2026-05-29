import json
import os
import random
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union

import sqlalchemy as sa
from sqlalchemy.orm import Session
# IMPORTANT: Import exc as sa_exc for robust error checking
from sqlalchemy import text, exc as sa_exc # Required for executing raw SQL commands and error handling

# Assuming your database connection and model imports are correct
from database.database import Base, engine, SessionLocal, get_db, DATABASE_URL
from database.models import * 
from database import models 
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status, APIRouter

from routers.login import get_current_user 
# Assuming User, get_current_user, get_db are defined/imported elsewhere

router = APIRouter(prefix="/users/me/email", tags=["Email Verification"])

# --- CONFIGURATION FOR EMAIL SENDING ---
# Credentials come from the environment so they are never committed to the
# repo (the previously hardcoded Gmail app password has been removed and must
# be rotated). See utils/mailer.py and .env.example.
PORT = int(os.getenv("SMTP_PORT", "465"))  # SSL Port
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
LOGIN = os.getenv("SMTP_LOGIN", "")
PASSWORD = os.getenv("SMTP_APP_PASSWORD", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", LOGIN)

# In-Memory Store for Verification Codes (Used temporarily)
# Structure: {user_id: {"email": str, "code": str, "expiry": datetime}}
VERIFICATION_CODES: Dict[int, Dict[str, Union[str, datetime]]] = {}


# --- PYDANTIC MODELS ---
class EmailVerificationRequest(BaseModel):
    """Model for requesting a verification code to a new email."""
    email: str

class EmailVerificationConfirm(BaseModel):
    """Model for confirming the received verification code."""
    code: str


# --- API ENDPOINTS FOR EMAIL VERIFICATION ---

@router.post("/verification-code", status_code=status.HTTP_202_ACCEPTED)
def send_email_verification_code(
    request: EmailVerificationRequest,
    User: models.User = Depends(get_current_user),
):
    """
    1. Generates a 5-digit code.
    2. Stores the code and the *target* email (from the request body) in memory.
    3. Sends the code to the provided email address.
    """
    user_id = User.id
    new_email = request.email.lower() # Normalize email
    
    # 1. Generate the 5-digit code and expiry time
    verification_code = str(random.randint(10000, 99999))
    expiry_time = datetime.now() + timedelta(minutes=5) # Code expires in 5 minutes
    
    # 2. Store the code, target email, and expiry time
    VERIFICATION_CODES[user_id] = {
        "email": new_email,
        "code": verification_code,
        "expiry": expiry_time
    }
    
    # 3. Create the email message (Improved look)
    em = EmailMessage()
    em["From"] = SENDER_EMAIL
    em["To"] = new_email
    em["Subject"] = "Verify Your Email Address"
    
    html_content = f"""
    <html>
        <body style="font-family: 'Inter', sans-serif; background-color: #f7f7f7; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);">
                <div style="background-color: #0d47a1; color: white; padding: 20px; text-align: center;">
                    <h1 style="margin: 0; font-size: 24px;">Email Verification</h1>
                </div>
                
                <div style="padding: 30px;">
                    <p style="font-size: 16px; color: #333;">Hello <strong>{User.username}</strong>,</p>
                    <p style="font-size: 16px; color: #555;">You recently requested to add or update your email address. Please use the verification code below to confirm this action:</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <span style="display: inline-block; background-color: #e3f2fd; color: #0d47a1; font-size: 32px; font-weight: bold; padding: 15px 25px; border-radius: 8px; letter-spacing: 5px;">
                            {verification_code}
                        </span>
                    </div>
                    
                    <p style="font-size: 14px; color: #d32f2f; text-align: center;">
                        <strong>IMPORTANT: This code expires in 5 minutes.</strong>
                    </p>
                    
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 25px 0;">
                    
                    <p style="font-size: 12px; color: #777; text-align: center;">
                        If you did not request this email address change, please ignore this message.
                    </p>
                </div>
            </div>
        </body>
    </html>
    """
    
    em.set_content(f"Your verification code is: {verification_code}. It expires in 5 minutes.", subtype='plain')
    em.add_alternative(html_content, subtype='html')

    context = ssl.create_default_context()
    
    try:
        # 4. Send the email
        with smtplib.SMTP_SSL(SMTP_SERVER, PORT, context=context) as smtp:
            smtp.login(LOGIN, PASSWORD)
            smtp.sendmail(SENDER_EMAIL, new_email, em.as_string())
            return {"message": f"Verification code sent to {new_email}", "expiry_minutes": 5}
    
    except Exception as e:
        print(f"Error sending email: {e}")
        del VERIFICATION_CODES[user_id] # Clean up temporary state on failure
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email. Please check server logs and configuration."
        )


@router.post("/verification")
def verify_email_code(
    confirm_data: EmailVerificationConfirm,
    User: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    1. Verifies the provided 5-digit code against the stored code.
    2. If valid and not expired, updates the UserProfile.email and sets is_verified=True.
    """
    user_id = User.id
    code = confirm_data.code
    stored_data = VERIFICATION_CODES.get(user_id)
    
    if not stored_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending verification request. Please request a new code."
        )

    # 1. Check for expiration
    if datetime.now() > stored_data["expiry"]:
        del VERIFICATION_CODES[user_id] # Clear the expired code
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired. Please request a new one."
        )

    # 2. Check for code match
    if stored_data["code"] != code:
        # Allow retries until expiry
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code."
        )

    # 3. Code is valid: Update user profile in the database
    new_email = stored_data["email"] # The email the user tried to verify
    
    try:
        # Find the UserProfile object in the DB session
        user_profile = db.query(models.User).filter(models.User.userid == user_id).first()
        
        if user_profile:
            # Update the email and verification status
            user_profile.email = new_email
            # We assume the 'is_verified' field was added via quick_update_schema
            user_profile.is_verified = True
            db.commit()
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found for database update."
            )
        
    except Exception as e:
        db.rollback()
        print(f"Database update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification failed during database update. Please try again."
        )
    finally:
        # 4. Clear the used code
        if user_id in VERIFICATION_CODES:
            del VERIFICATION_CODES[user_id]
        
    return {"message": "Email successfully verified and updated!", "email": new_email, "is_verified": True}



# NOTE ON SCHEMA CHANGES: Base.metadata.create_all() only creates tables
# that do not exist. If you change a model (like adding the 'owner' column
# to StartedTest), you must manually delete your old database file (e.g., 'test.db')
# and run this script again to apply the new schema OR use the quick_update_schema
# function below for incremental changes.
#
# NOTE: Calling Base.metadata.create_all(...) at import time forces a round
# trip to Postgres for every worker that imports this module, which slows
# cold starts. Schema management belongs in Alembic migrations, so we keep
# the helper available but no longer run it implicitly.




def quick_update_schema(database_url: str):
    """
    Connects to the database and executes raw SQL to add the missing columns
    to the 'user_profile' table: 'email' and 'is_verified'.
    
    WARNING: Use this method ONLY for quick local testing.
    """
    # Create a new engine instance for the update, ensuring the URL is correct
    engine = sa.create_engine(database_url) 
    
    # Define the raw SQL commands
    # The commands use ALTER TABLE to modify the existing user_profile table.
    sql_commands = [
        # Add the 'email' column (allows NULL values)
        text("""
            ALTER TABLE user_profile 
            ADD COLUMN email VARCHAR(30) NULL;
        """),
        
        # Add the 'is_verified' column (MANDATORY for your API code)
        # Setting DEFAULT FALSE ensures existing rows are not left NULL.
        text("""
            ALTER TABLE user_profile 
            ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT FALSE;
        """)
    ]
    
    print(f"Connecting to database to apply schema updates: {database_url}")
    
    try:
        # Use a transaction (begin/commit) for safe execution
        with engine.begin() as connection:
            for command in sql_commands:
                try:
                    connection.execute(command)
                    print(f"Successfully executed: {command.statement}")
                # FIX: Swapping to DatabaseError to more robustly catch OperationalError
                # raised by SQLite when columns already exist.
                except sa_exc.DatabaseError as e:
                    # Check for "column already exists" error specific to SQLite/PostgreSQL
                    error_message = str(e).lower()
                    if "duplicate column" in error_message or "already exists" in error_message:
                        print(f"Warning: Column already exists. Ignoring command: {command.statement}")
                    else:
                        # If it's another type of database error, re-raise it
                        raise
            
            print("\nDatabase schema update complete. 'email' and 'is_verified' columns are ready.")

    except Exception as e:
        print(f"\n--- FATAL ERROR ---")
        print(f"Could not connect or run updates: {e}")
        print("Please check your DATABASE_URL and ensure your DB server is running.")


# # Create tables in the database
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
    into the given SQLAlchemy session, ensuring data exists without duplicates.
    """
    company_email = "hr@techtest.com"
    user_username = "user"

    print("--- Inserting Test Data ---")
    
    # --- 1. Create Company (Avoid IntegrityError) ---
    company1 = db.query(models.Company).filter(models.Company.email == company_email).first()
    if not company1:
        company1 = models.Company(
            name="TechTest Corp",
            email=company_email,
            INN="9876543210",
            phone_number="555-9000"
        )
        db.add(company1)
        db.commit()
        db.refresh(company1)
        print(f"1. Created Company: {company1.name} (ID: {company1.id})")
    else:
        print(f"1. Company already exists: {company1.name} (ID: {company1.id})")

    # --- 2. Create User ---
    user1 = db.query(models.User).filter(models.User.username == user_username).first()
    if not user1:
        user1 = models.User(
            username=user_username,
            role="Candidate",
            password="1234", # Should be hashed in production
        )
        db.add(user1)
        db.commit()
        db.refresh(user1)
        print(f"2. Created User: {user1.username} (ID: {user1.id})")
    else:
        print(f"2. User already exists: {user1.username} (ID: {user1.id})")

    # --- 3. Create User Profile (Only if it doesn't exist) ---
    # We assume a profile should exist if the user was just created, 
    # but we check to prevent integrity errors on the 'userid' foreign key/primary key.
    profile1 = db.query(models.User).filter(models.User.userid == user1.id).first()
    if not profile1:
        profile1 = models.User(
            userid=user1.id,
            name="Alex",
            surname="Smith",
            age=28
        )
        db.add(profile1)
        print("3. Created UserProfile.")
    else:
        print("3. UserProfile already exists.")

    # --- 4. Create Questions ---
    # Fetch questions needed for foreign key constraint in UserAnswer
    q_python = db.query(models.Question).filter(models.Question.category == 'python').first()
    q_math = db.query(models.Question).filter(models.Question.category == 'math').first()
    print(f"4. Re-fetched sample questions for FKs.")
    
    # --- 5. Create StartedTest records (Ensure these aren't duplicated if possible) ---
    # For testing, we can check if the active test already exists for this user/owner combo
    active_test = db.query(models.StartedTest).filter(
        models.StartedTest.user_id == user1.id,
        models.StartedTest.owner == company1.id,
        models.StartedTest.is_active == True
    ).first()

    if not active_test:
        # A. Active/In-progress Test (for /active_test)
        active_test = models.StartedTest(
            user_id=user1.id,
            owner=company1.id,
            deadline=datetime.now() + timedelta(days=5),
            current_level=2,
            current_score=5.5,
            is_active=True
        )
        db.add(active_test)
        print("5. Created 1 Active Test.")
    else:
         print("5. Active Test already exists.")

    # B. Passive/Completed Test (We usually let these accumulate, but for seeding simplicity, we check if one exists)
    completed_test = db.query(models.StartedTest).filter(
        models.StartedTest.user_id == user1.id,
        models.StartedTest.owner == company1.id,
        models.StartedTest.is_active == False
    ).first()

    if not completed_test:
        completed_test = models.StartedTest(
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
        print("5. Created 1 Completed Test.")
    else:
        db.commit()
        print("5. Completed Test already exists.")

    # --- 6. Create a sample UserAnswer for the completed test (Only if it doesn't exist) ---
    if q_python:
        answer = db.query(models.UserAnswer).filter(
            models.UserAnswer.user_id == user1.id,
            models.UserAnswer.question_id == q_python.id
        ).first()

        if not answer:
            answer = models.UserAnswer(
                user_id=user1.id,
                question_id=q_python.id,
                user_answer="str",
                is_correct=True,
                score_awarded=q_python.points
            )
            db.add(answer)
            db.commit()
            print("6. Added sample UserAnswer for the completed test.")
        else:
            print("6. Sample UserAnswer already exists.")
        
    print("--- Test Data Insertion Complete ---")


if __name__ == "__main__":
    # 1. Apply schema changes (creates tables if they don't exist)
    Base.metadata.create_all(bind=engine) 
    
    # 2. Apply incremental schema changes (adds 'email' and 'is_verified' columns)
    quick_update_schema(DATABASE_URL)

    # 3. Seed the generic questions
    seed_questions() 

    # 4. Seed the company, user, test, and answer data
    db = SessionLocal()
    try:
        insert_test_data(db)
    finally:
        db.close()
