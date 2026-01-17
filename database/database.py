from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ✅ Replace with your actual MySQL credentials
#DATABASE_URL = "sqlite:///./test.db"

## internal url
# Updated with URL-encoded password
DATABASE_URL = "postgresql://postgres.wzdcbbbqjaledjfraolq:14042005Fayz.%24@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres"
#DATABASE_URL = "postgresql://fulstek1_asap:14042005Fayz.@167.235.222.200/fulstek1_hr"
## external url
#DATABASE_URL = "postgresql://asap:pzzPoFUjWFYEfblTYFRW8P46AMC7P6Yr@dpg-d4lfcl3e5dus73foo3i0-a.oregon-postgres.render.com/hrassistant_2k4y"

# Create SQLAlchemy engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL)  # PostgreSQL does NOT need connect_args


# Create a configured "Session" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our ORM models
Base = declarative_base()
# database/database.py

def get_db():
    db = SessionLocal()  # 1. Create the session
    try:
        yield db         # 2. Give the session to the router
    finally:
        db.close()       # 3. Close the session (Even if code crashes!)
