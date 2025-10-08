from sqlalchemy.orm import Session
from database.database import Base, engine, SessionLocal
from database import models

def create_tables():
    print("🔧 Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created successfully!")

def seed_default_data():
    """Optional: Add a default company and admin user if not exists"""
    db: Session = SessionLocal()

    # Check if a company exists
    company = db.query(models.Company).first()
    if not company:
        company = models.Company(
            name="Default Company",
            phone_number="123456789",
            INN="111111111",
            email="default@company.com"
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        print(f"🏢 Created default company: {company.name}")

    # Check if an admin user exists
    admin_user = db.query(models.User).filter_by(username="admin").first()
    if not admin_user:
        admin_user = models.User(
            username="admin",
            password="1234",  # ⚠️ hash this later!
            role="admin",
            company_id=company.id
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        print(f"👤 Created default admin user: {admin_user.username}")

    db.close()

if __name__ == "__main__":
    create_tables()
    seed_default_data()
