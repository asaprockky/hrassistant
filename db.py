from sqlalchemy import create_engine, text
from database.database import DATABASE_URL
   # same as in your server

engine = create_engine(DATABASE_URL)

# Write your ALTER TABLE statements here
statements = [
    "ALTER TABLE user_profile ADD COLUMN email VARCHAR(30);",
    # Add more columns if needed
]

with engine.connect() as conn:
    for stmt in statements:
        try:
            conn.execute(text(stmt))
            print(f"Executed: {stmt}")
        except Exception as e:
            print(f"Skipped (maybe exists): {stmt} -> {e}")
