from database.database import Base, engine, SessionLocal
from database import models

Base.metadata.create_all(bind=engine)
print("✅ Tables created/updated successfully!")
