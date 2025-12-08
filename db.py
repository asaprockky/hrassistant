from sqlalchemy import create_engine, text
from database.database import DATABASE_URL
from database.enums import Role
from sqlalchemy.orm import sessionmaker

from database.models import User
   # same as in your server


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def update_user_role(user_id: int, new_role=Role.USER):
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"User with id {user_id} not found.")
            return

        user.role = new_role
        session.commit()
        print(f"Updated user id={user_id} to role '{new_role.name}'")
    except Exception as e:
        session.rollback()
        print("Error:", e)
    finally:
        session.close()

if __name__ == "__main__":
    update_user_role(user_id=1, new_role=Role.USER)