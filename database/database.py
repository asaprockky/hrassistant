import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# The connection string is read from the DATABASE_URL environment variable so
# credentials are never committed to the repo. The previously hardcoded
# production URL has been removed and its password must be rotated (see PR
# notes / .env.example). Falls back to a local Postgres for development.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres@127.0.0.1:5432/postgres",
)

# Create SQLAlchemy engine
# Pool tuning:
# - pool_pre_ping recycles dead connections (important when the DB sits behind
#   a transaction pooler like Supabase/PgBouncer that can drop sockets).
# - pool_recycle prevents stale connections from being reused after long idle.
# - pool_size / max_overflow keep us within the pooler's connection budget
#   while still allowing burst concurrency.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=10,
        max_overflow=20,
    )


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
