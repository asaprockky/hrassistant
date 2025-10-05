from database.database import Base, engine, SessionLocal
from database import models

# ✅ Create tables in the database
Base.metadata.create_all(bind=engine)

# Optional: test inserting data
db = SessionLocal()

# Example: create company
new_company = models.Company(
    name="FlexFin",
    phone_number="998901234567",
    INN="123456789",
    email="info@flexfin.uz"
)
db.add(new_company)
db.commit()
db.refresh(new_company)

# Example: create user linked to company
new_user = models.User(
    username="Abdulfayiz",
    role="admin",
    password="hashedpassword",
    company_id=new_company.id
)
db.add(new_user)
db.commit()

print("✅ Tables created and sample data inserted!")
