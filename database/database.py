from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ✅ Replace with your actual MySQL credentials
DATABASE_URL = "sqlite:///./test.db"

## internal url
#DATABASE_URL = "postgresql://asap:SC4DMhaYXca3I5KOrKYGZnHVQuFcXe05@dpg-d49n53f5r7bs73dv8sug-a/hrassistant"
## external url
#DATABASE_URL = "postgresql://asap:SC4DMhaYXca3I5KOrKYGZnHVQuFcXe05@dpg-d49n53f5r7bs73dv8sug-a.oregon-postgres.render.com/hrassistant"

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
