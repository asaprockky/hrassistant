from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ✅ Replace with your actual MySQL credentials
DATABASE_URL = "sqlite:///./test.db"

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    connect_args = {"check_same_thread": False}
)

# Create a configured "Session" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our ORM models
Base = declarative_base()
