from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://posgres:1234@localhost:5432/hrtest"

engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("Connection OK:", result.scalar())
except Exception as e:
    print("Connection FAILED:", e)
