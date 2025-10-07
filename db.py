from sqlalchemy.orm import Session
from database.database import engine, Base
from database.models import User, Company

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# Create a new database session
from sqlalchemy.orm import sessionmaker
SessionLocal = sessionmaker(bind=engine)
db: Session = SessionLocal()

# Example: If you have a company already
company = db.query(Company).first()
if not company:
    company = Company(name="Default Company", phone_number="123456", INN="111", email="test@company.com")
    db.add(company)
    db.commit()
    db.refresh(company)

# Create a new user
new_user = User(
    username="i7",
    password="1234",  # ⚠️ In production, always hash passwords!
    role="admin",
    company_id=company.id
)

db.add(new_user)
db.commit()
db.refresh(new_user)

print(f"Created user: {new_user.username} with ID {new_user.id}")
db.close()
