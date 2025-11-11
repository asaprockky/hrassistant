import random
from fastapi import APIRouter
from sqlalchemy import func
from database.database import SessionLocal
from database.models import Question, User, UserAnswer
from schemas.user_schema import AnswerCreate, AnswerResponse
from routers.login import get_current_user

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_question_by_level(level: int):
    db = SessionLocal()
    question = db.query(Question)\
                 .filter(Question.difficulty_level == level)\
                 .order_by(func.random())\
                 .first()
    
    return question
    



def get_difficulty(difficulty):
    if difficulty <= 3:
        return 'easy'
    elif difficulty <= 6:
        return 'medium'
    else :
        return 'hard'

user_state = {"level": 1, "score": 0.0}


router = APIRouter()

@router.post("/submit_answer", response_model=AnswerResponse)
def submit_answer(answer: AnswerCreate, user: User = Depends(get_current_user), db: User = Depends(get_current_user)):
    user_id = user.id

    # update level & points
    if answer.correct:
        user_state["level"] = min(9, user_state["level"] + 1)
    else:
        user_state["level"] = max(1, user_state["level"] - 1)

    points = round(1 + user_state["level"] / 10, 1)
    user_state["score"] += points

    # save answer to DB
    new_answer = UserAnswer(
        answer_text=answer.answer_text,
        candidate_id=user_id,
        question_id=answer.question_id
    )
    db.add(new_answer)
    db.commit()
    db.refresh(new_answer)

    # get next question info (functions you already have)
    q = get_question_by_level(level=user_state["level"])
    difficulty = get_difficulty(user_state["level"])

    return AnswerResponse(
        question_id=q.id,
        answer_text=new_answer.answer,
        points_awarded=points,
        total_score=round(user_state["score"], 2),
        level=user_state["level"],
        difficulty=difficulty
    )

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

def get_question():
    print("api has been used")
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
