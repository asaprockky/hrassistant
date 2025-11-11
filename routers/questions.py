import random
from fastapi import APIRouter
from sqlalchemy import func
from database.database import SessionLocal
from database.models import Question
from schemas.user_schema import Answer



def get_question_by_level(level: int):
    db = SessionLocal()
    question = db.query(Question)\
                 .filter(Question.difficulty_level == level)\
                 .order_by(func.random())\
                 .first()
    db.close()



def get_difficulty(difficulty):
    if difficulty <= 3:
        return 'easy'
    elif difficulty <= 6:
        return 'medium'
    else :
        return 'hard'

user_state = {"level": 1, "score": 0.0}


router = APIRouter()

@router.post('/submit_answer')
def submit_answer(answer : Answer):
    global user_state
    if answer.correct:
        user_state["level"] = min(9, user_state["level"] + 1)
    else:
        user_state["level"] = max(1, user_state["level"] - 1)
    points = round(1 + user_state["level"] / 10, 1)
    
    q = get_question_by_level(level= user_state["level"])
    difficulty = get_difficulty(user_state["level"])

    return {
        "question": q.text,
        "difficulty": difficulty,
        "level": user_state["level"],
        "points_awarded": points,
        "total_score": round(user_state["score"], 2),
    }


@router.get("/get_question")
def get_question():
    level = user_state["level"]
    difficulty = get_difficulty(level)
    q = get_question_by_level(level)
    return {
        "question": q.text,
        "options": q.options,
        "difficulty": difficulty,
        "level": level,
        "indicator": f"Current Level: {level}/9"
    }
