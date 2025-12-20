import datetime
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

# Adjust these imports to match your project structure
from database.database import get_db
from database.models import Practice, Question, TestSession, UserAnswer
from routers.login import get_current_user
from schemas.user_schema import TestStatusResponse, AnswerCreate

router = APIRouter()

@router.post("/testing/start-test/{practice_id}")
def start_test(
    practice_id: uuid.UUID, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user)
):
    user_id = current_user.id
    
    # 1. Validate Practice
    practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
    if not practice or not practice.is_valid:
        raise HTTPException(status_code=404, detail="Practice not found or inactive")
    
    # Use timezone-aware comparison
    if practice.deadline < datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="Practice deadline has passed")

    # 2. Check for existing active session
    existing_session = db.query(TestSession).filter(
        TestSession.user_id == user_id,
        TestSession.practice_id == practice_id,
        TestSession.is_finished == False
    ).first()

    if existing_session:
        return {"message": "Resuming existing test session", "session_id": existing_session.session_id}

    # 3. Create new session in DB
    new_session = TestSession(
        practice_id=practice_id,
        user_id=user_id,
        overall_points=0,
        is_finished=False
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {"message": "Test Started", "session_id": new_session.session_id}


@router.get("/testing/get-question/{session_id}")
def get_next_question(
    session_id: uuid.UUID, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user)
):
    user_id = current_user.id
    
    # 1. Get the active session
    session = db.query(TestSession).filter(
        TestSession.user_id == user_id,
        TestSession.session_id == session_id,
        TestSession.is_finished == False
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="No active test session found.")

    # 2. Get Practice details using the PRACTICE_ID stored in the session
    # BUG FIX: You previously used 'session_id' here, which was wrong.
    practice = db.query(Practice).filter(Practice.practice_id == session.practice_id).first()
    
    if not practice:
        raise HTTPException(status_code=404, detail="Practice data not found")

    # 3. Get IDs of questions already answered in this session
    answered_ids = [ans.question_id for ans in session.answers]

    # 4. Find the first question in the Practice list that hasn't been answered
    next_question_id = None
    if practice.question_ids:
        for q_id in practice.question_ids:
            if q_id not in answered_ids:
                next_question_id = q_id
                break
    
    if not next_question_id:
        # If no questions left, mark session as finished
        session.is_finished = True
        db.commit()
        return {"message": "Test Finished", "is_finished": True}

    # 5. Fetch the actual question object
    question = db.query(Question).filter(Question.id == next_question_id).first()
    
    if not question:
        raise HTTPException(status_code=500, detail="Question data invalid")

    return {
        "id": question.id,
        "text": question.text,
        "options": question.options,
        "category": question.category,
        "points": question.points
    }


@router.post("/testing/submit-answer/{session_id}", response_model=TestStatusResponse)
def submit_answer(
    session_id: uuid.UUID,
    answer_data: AnswerCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user) # BUG FIX: Removed type hint causing cast error
):
    user_id = current_user.id # BUG FIX: Extract ID manually

    # 1. Retrieve Session
    session = db.query(TestSession).filter(
        TestSession.user_id == user_id,
        TestSession.session_id == session_id,
        TestSession.is_finished == False
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Active session not found")

    # 2. Validate Question
    question = db.query(Question).filter(Question.id == answer_data.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # 3. Check Duplicate Answer
    existing_answer = db.query(UserAnswer).filter(
        UserAnswer.session_id == session.session_id,
        UserAnswer.question_id == answer_data.question_id
    ).first()
    
    if existing_answer:
        raise HTTPException(status_code=400, detail="Question already answered")

    # 4. Check Logic
    is_correct = question.correct_answer.strip().lower() == answer_data.user_answer.strip().lower()
    points_awarded = question.points if is_correct else 0.0

    # 5. Save User Answer
    user_answer_entry = UserAnswer(
        session_id=session.session_id,
        question_id=question.id,
        user_answer=answer_data.user_answer,
        is_correct=is_correct,
        points_awarded=points_awarded
    )
    db.add(user_answer_entry)
    
    # 6. Update Session Score
    session.overall_points += points_awarded
    db.commit()
    practice_id = session.practice_id
    # 7. Check if Test is Finished
    practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
    
    # Ensure practice and question_ids exist
    if practice and practice.question_ids:
        total_questions = len(practice.question_ids)
        answered_count = db.query(UserAnswer).filter(UserAnswer.session_id == session.session_id).count()
        
        is_finished = answered_count >= total_questions
        
        if is_finished:
            session.is_finished = True
            db.commit()
    else:
        is_finished = False

    return {
        "message": "Answer submitted",
        "is_correct": is_correct,
        "correct_answer": question.correct_answer,
        "points_awarded": points_awarded,
        "is_test_finished": is_finished
    }

@router.get("/testing/result/{practice_id}")
def get_test_result(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user) # BUG FIX: Removed type hint causing cast error
):
    user_id = current_user.id # BUG FIX: Extract ID manually

    # Retrieve the finished session
    session = db.query(TestSession).filter(
        TestSession.user_id == user_id,
        TestSession.practice_id == practice_id
    ).order_by(TestSession.started_time.desc()).first()

    if not session:
        raise HTTPException(status_code=404, detail="No session found")

    return {
        "practice_id": practice_id,
        "total_score": session.overall_points,
        "is_finished": session.is_finished,
        "started_at": session.started_time
    }