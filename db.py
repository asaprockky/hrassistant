import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
# Make sure to import Base here
from database.database import engine, SessionLocal, Base 
from database.enums import Role
from database.models import (
    Company, User, Created_Vacancy, Question, Practice
)

def seed_sample_data():
    print("Connecting to PostgreSQL to insert sample data...")
    
    # --- ADD THIS LINE TO CREATE TABLES IN SUPABASE ---
    print("Creating tables if they don't exist...")
    Base.metadata.create_all(bind=engine)
    # --------------------------------------------------

    # Clear existing data to avoid UUID conflicts
    with engine.connect() as connection:
        try:
            print("Cleaning existing data...")
            connection.execute(text("TRUNCATE TABLE user_answers, test_session, practice, user_questions, candidates, created_vacancies, users, companies CASCADE"))
            connection.commit()
        except Exception as e:
            # If truncate fails because tables were just created and are empty, we can skip
            print(f"Truncate skipped or failed: {e}")

    db = SessionLocal()
    
    try:
        # 1. Create Sample Company
        comp_id = uuid.uuid4()
        sample_company = Company(
            id=comp_id,
            name="NEXUS PRO Tech",
            phone_number="+998901234567",
            INN="123456789",
            email="hr@nexuspro.uz"
        )
        db.add(sample_company)

        # 2. Create Sample Users (Password = 1234)
        admin_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        admin_user = User(
            id=admin_id,
            username="admin_fayz",
            role=Role.ADMIN,
            password="1234",
            company_id=comp_id,
            name="Abdulfayz",
            surname="Shokirov",
            age=21,
            email="admin@fulstek.uz"
        )
        
        sample_user = User(
            id=user_id,
            username="sample_candidate",
            role=Role.USER,
            password="1234",
            name="Sample",
            surname="User",
            age=25,
            email="user@example.com"
        )
        db.add_all([admin_user, sample_user])
        db.flush() 

        # 3. Create Sample Questions
        q_ids = [uuid.uuid4(), uuid.uuid4()]
        questions = [
            Question(
                id=q_ids[0],
                text="What is the primary goal of a Data Scientist?",
                difficulty_level=1,
                correct_answer="Extracting insights from data",
                options={'a': 'Extracting insights from data', 'b': 'Building hardware'},
                category="Data Science",
                points=10.0
            ),
            Question(
                id=q_ids[1],
                text="Which SQL clause is used to filter records?",
                difficulty_level=1,
                correct_answer="WHERE",
                options={'a': 'ORDER BY', 'b': 'WHERE'},
                category="SQL",
                points=5.0
            )
        ]
        db.add_all(questions)

        # 4. Create Sample Practice
        practice_id = uuid.uuid4()
        sample_practice = Practice(
            practice_id=practice_id,
            title="Initial Technical Assessment",
            question_ids=q_ids,
            tags=["SQL", "Python"],
            user_emails=["user@example.com"],
            deadline=datetime.now(timezone.utc) + timedelta(days=7),
            is_valid=True
        )
        db.add(sample_practice)

        db.commit()
        print("✅ Tables created and sample data seeded successfully!")

    except Exception as e:
        db.rollback()
        print(f"❌ Error during seeding: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_sample_data()