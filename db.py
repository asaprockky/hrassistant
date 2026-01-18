import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import text

# Ensure these imports match your actual file structure
from database.database import engine, SessionLocal, Base 
from database.enums import Role

# ADDED PracticeAssignment to imports so the table gets created
from database.models import Company, User, Question, Practice, PracticeAssignment

def seed_sample_data():
    print("🚀 Starting Data Seeding...")
    
    # 1. RESET SCHEMA (Crucial for model updates)
    print("⚠️  Dropping and Recreating tables to apply Schema changes...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    
    try:
        # 2. Create Sample Company
        comp_id = uuid.uuid4()
        sample_company = Company(
            id=comp_id,
            name="NEXUS PRO Tech",
            phone_number="+998901234567",
            INN="123456789",
            email="hr@nexuspro.uz"
        )
        db.add(sample_company)

        # 3. Create Users
        admin_user = User(
            id=uuid.uuid4(),
            username="admin",
            role=Role.ADMIN,
            password="1234", # Hash this in production!
            company_id=comp_id,
            name="Abdulfayz",
            surname="Shokirov",
            age=21,
            email="admin@fulstek.uz"
        )
        
        sample_candidate = User(
            id=uuid.uuid4(),
            username="user",
            role=Role.USER,
            password="1234",
            name="Sample",
            surname="User",
            age=25,
            email="user@example.com"
        )
        db.add_all([admin_user, sample_candidate])
        db.flush() 

        # 4. Create Questions
        
        # --- Question 1: Data Science ---
        q1_id = uuid.uuid4()
        opt_1a = uuid.uuid4() # Correct
        opt_1b = uuid.uuid4()
        
        q1 = Question(
            id=q1_id,
            text="What is the primary goal of a Data Scientist?",
            difficulty_level=1,
            category="Data Science",
            points=10.0,
            options=[
                {"id": str(opt_1a), "text": "Extracting insights from data"},
                {"id": str(opt_1b), "text": "Building computer hardware"}
            ],
            correct_answer=opt_1a 
        )

        # --- Question 2: SQL ---
        q2_id = uuid.uuid4()
        opt_2a = uuid.uuid4()
        opt_2b = uuid.uuid4() # Correct

        q2 = Question(
            id=q2_id,
            text="Which SQL clause is used to filter records?",
            difficulty_level=1,
            category="SQL",
            points=5.0,
            options=[
                {"id": str(opt_2a), "text": "ORDER BY"},
                {"id": str(opt_2b), "text": "WHERE"}
            ],
            correct_answer=opt_2b 
        )
        
        db.add_all([q1, q2])

        # 5. Create Practice (UPDATED)
        practice_id = uuid.uuid4()
        
        sample_practice = Practice(
            practice_id=practice_id,
            title="Initial Technical Assessment",
            question_ids=[q1_id, q2_id],
            tags=["SQL", "Python"],
            # REMOVED: user_emails=["user@example.com"],
            deadline=datetime.now(timezone.utc) + timedelta(days=7),
            is_valid=True
        )
        
        # --- NEW ASSIGNMENT LOGIC ---
        # Directly append the user object to the relationship list
        # This automatically creates the entry in the 'practice_assignments' table
        sample_practice.allowed_users.append(sample_candidate)

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