import random
from fastapi import APIRouter
from sqlalchemy import func
from database.database import SessionLocal
from database.models import Question, User, UserAnswer, StartedTest
from schemas.user_schema import AnswerCreate, AnswerResponse
from routers.login import get_current_user
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_question_by_level(db: Session, level: int):
    question = db.query(Question)\
                 .filter(Question.difficulty_level == level)\
                 .order_by(func.random())\
                 .first()
    return question



def get_difficulty_label(difficulty):
    if difficulty <= 3: return 'easy'
    elif difficulty <= 6: return 'medium'
    else : return 'hard'

user_state = {"level": 1, "score": 0.0}


router = APIRouter()

@router.post("/submit_answer", response_model=AnswerResponse)
def submit_answer(
    answer: AnswerCreate, 
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    # 1. Retrieve the user's current test state
    test_session = db.query(StartedTest).filter(
        StartedTest.user_id == user.id, 
        StartedTest.is_active == True
    ).first()

    if not test_session:
        raise HTTPException(status_code=400, detail="Start a test first")

    # 2. Get the actual question to verify correctness (don't trust the client completely)
    db_question = db.query(Question).filter(Question.id == answer.question_id).first()
    if not db_question:
        raise HTTPException(status_code=404, detail="Question not found")

    # 3. Determine correctness (Logic can be here or passed from frontend if trusted)
    # Assuming frontend sends `correct` boolean, but safer to check against db_question.correct_answer here
    is_correct = answer.correct 

    # 4. Calculate Logic
    if is_correct:
        test_session.current_level = min(9, test_session.current_level + 1)
        points = round(1 + test_session.current_level / 10, 1)
    else:
        test_session.current_level = max(1, test_session.current_level - 1)
        points = 0.0

    test_session.current_score += points

    # 5. Save Answer
    new_answer = UserAnswer(
        answer_text=answer.answer_text,
        user_id=user.id,           # Fixed: was candidate_id
        question_id=answer.question_id,
        is_correct=is_correct,
        score_awarded=points
    )
    
    db.add(new_answer)
    db.commit() # Commits both the new answer AND the updated test_session state
    db.refresh(test_session)

    # 6. Prepare next question data
    q = get_question_by_level(db, test_session.current_level)
    difficulty = get_difficulty_label(test_session.current_level)

    return AnswerResponse(
        question_id=q.id if q else None,
        answer_text=new_answer.answer_text,
        points_awarded=points,
        total_score=round(test_session.current_score, 2),
        level=test_session.current_level,
        difficulty=difficulty
    )

@router.get("/get_question")
def get_question():
    level = user_state["level"]
    difficulty = get_difficulty_label(level)
    q = get_question_by_level(level)
    return {
        "question": q.text,
        "options": q.options,
        "difficulty": difficulty,
        "level": level,
        "indicator": f"Current Level: {level}/9"
    }

@router.get("/start_test")
def start_test(
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    # Check if an active test already exists
    active_test = db.query(StartedTest).filter(
        StartedTest.user_id == user.id, 
        StartedTest.is_active == True
    ).first()

    if not active_test:
        # Create a new test session in DB
        active_test = StartedTest(user_id=user.id, current_level=1, current_score=0.0)
        db.add(active_test)
        db.commit()
        db.refresh(active_test)

    # Fetch a question based on the stored level
    q = get_question_by_level(db, active_test.current_level)
    
    if not q:
        raise HTTPException(status_code=404, detail="No questions found for this level")

    return {
        "question": q.text,
        "question_id": q.id,
        "options": q.options,
        "difficulty": get_difficulty_label(active_test.current_level),
        "level": active_test.current_level,
        "indicator": f"Current Level: {active_test.current_level}/9"
    }

