from sqlalchemy.orm import Session
from database.database import Base, engine
from database.database import SessionLocal
from database.models import * 
from database import models
import json


# Create tables in the database
def seed_questions():
    db: Session = SessionLocal()

    questions = [
        # --- MATH (easy 1-3) ---
        ("math", "2 + 2 = ?", "4", ["3", "4", "5", "6"], 1, 1.1),
        ("math", "5 - 3 = ?", "2", ["1", "2", "3", "4"], 1, 1.1),
        ("math", "10 / 2 = ?", "5", ["4", "5", "6", "8"], 2, 1.2),
        ("math", "3 * 4 = ?", "12", ["9", "10", "12", "14"], 2, 1.2),
        ("math", "√81 = ?", "9", ["7", "8", "9", "10"], 3, 1.3),
        ("math", "12 * 8 = ?", "96", ["84", "96", "108", "120"], 4, 1.4),
        ("math", "log2(64) = ?", "6", ["4", "5", "6", "7"], 5, 1.5),
        ("math", "sin(90°) = ?", "1", ["0", "1", "0.5", "-1"], 6, 1.6),
        ("math", "15² = ?", "225", ["200", "215", "225", "250"], 7, 1.7),
        ("math", "√625 = ?", "25", ["20", "25", "30", "35"], 7, 1.7),
        ("math", "8³ = ?", "512", ["256", "512", "128", "1024"], 8, 1.8),
        ("math", "cos(0°) = ?", "1", ["0", "1", "-1", "0.5"], 9, 1.9),

        # --- PYTHON (easy to hard 1-9) ---
        ("python", "What is the output of print(2 + 3 * 4)?", "14", ["20", "14", "24", "12"], 1, 1.1),
        ("python", "Which keyword defines a function in Python?", "def", ["func", "function", "def", "lambda"], 2, 1.2),
        ("python", "What is the output of len('ChatGPT')?", "7", ["6", "7", "8", "5"], 3, 1.3),
        ("python", "Which collection is ordered and immutable?", "tuple", ["list", "set", "tuple", "dict"], 4, 1.4),
        ("python", "What does the 'self' keyword refer to in a class?", "the instance", ["the class", "a module", "the instance", "None"], 5, 1.5),
        ("python", "What is the output of 3 == 3.0 in Python?", "True", ["True", "False", "Error", "None"], 6, 1.6),
        ("python", "Which decorator is used for static methods?", "@staticmethod", ["@classmethod", "@staticmethod", "@property", "@static"], 7, 1.7),
        ("python", "What will print(type(lambda x: x)) show?", "<class 'function'>", ["<class 'lambda'>", "<class 'func'>", "<class 'function'>", "<lambda>"], 8, 1.8),
        ("python", "What’s the output of [i for i in range(3)]?", "[0, 1, 2]", ["[1,2,3]", "[0,1,2]", "(0,1,2)", "{0,1,2}"], 9, 1.9)
    ]

    for q in questions:
        user_question = models.Question(
            category=q[0],
            text=q[1],
            correct_answer=q[2],
            options=q[3],
            difficulty_level=q[4],
            points=q[5]
        )
        db.add(user_question)

    db.commit()
    db.close()
    print("✅ Questions added successfully!")

if __name__ == "__main__":
    seed_questions()
