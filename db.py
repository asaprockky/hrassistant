# init_db.py
import asyncio
from database.database import engine, Base
# Import all your models here so SQLAlchemy knows about them
from database.models import Company, User, Created_Vacancy, Candidate, Question, UserAnswer, StartedTest

def reset_database():
    print("🗑️  Dropping all existing tables...")
    # This deletes all tables defined in your models
    Base.metadata.drop_all(bind=engine)
    print("✅ Tables dropped.")

    print("🛠️  Creating new tables with UUID support...")
    # This creates the new tables based on your updated models
    Base.metadata.create_all(bind=engine)
    print("✅ New tables created successfully!")

if __name__ == "__main__":
    reset_database()