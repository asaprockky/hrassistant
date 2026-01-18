import datetime
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime


# Adjust these imports to match your project structure
from database.database import get_db
from database.models import Practice, PracticeAssignment, Question, TestSession, UserAnswer
from routers.login import get_current_user
from schemas.user_schema import TestStatusResponse, AnswerCreate

router = APIRouter()


# --- Endpoints ---

@router.post("/testing/start-test/{practice_id}")
def start_test(
    practice_id: uuid.UUID, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user)
):
    user_id = current_user.id
    # In your start_test endpoint
    assignment = db.query(PracticeAssignment).filter(
        PracticeAssignment.practice_id == practice_id,
        PracticeAssignment.user_id == current_user.id
    ).first()

    if not assignment:
        raise HTTPException(status_code=403, detail="You are not assigned to this test.")
    
    # 1. Validate Practice
    practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
    if not practice or not practice.is_valid:
        raise HTTPException(status_code=404, detail="Practice not found or inactive")
    
    # Check Deadline (Timezone aware)
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
        session_id=uuid.uuid4(),  # Generate ID explicitly
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

    # 2. Get Practice details
    practice = db.query(Practice).filter(Practice.practice_id == session.practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice data not found")

    # 3. Get IDs of questions already answered
    # We query the UserAnswer table directly for efficiency
    answered_ids = db.query(UserAnswer.question_id).filter(
        UserAnswer.session_id == session.session_id
    ).all()
    # Flatten list of tuples [(uuid,), (uuid,)] -> [uuid, uuid]
    answered_ids = [aid[0] for aid in answered_ids]

    # 4. Find the first unanswered question ID
    next_question_id = None
    if practice.question_ids:
        for q_id in practice.question_ids:
            if q_id not in answered_ids:
                next_question_id = q_id
                break
    
    # If no questions left, finish the test
    if not next_question_id:
        session.is_finished = True
        db.commit()
        return {"message": "Test Finished", "is_finished": True}

    # 5. Fetch Question Object
    question = db.query(Question).filter(Question.id == next_question_id).first()
    if not question:
        raise HTTPException(status_code=500, detail="Question data invalid")

    return {
        "id": question.id,
        "text": question.text,
        "options": question.options, # Returns the list of objects: [{"id":..., "text":...}]
        "category": question.category,
        "points": question.points
    }


@router.post("/testing/submit-answer/{session_id}")
def submit_answer(
    session_id: uuid.UUID,
    answer_data: AnswerCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id 

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

    # 4. Check Logic (UPDATED FOR UUID)
    # Convert both to strings for safe comparison
    # question.correct_answer is a UUID object; answer_data.user_answer is a string
    is_correct = str(question.correct_answer) == str(answer_data.user_answer)
    
    points_awarded = question.points if is_correct else 0.0

    # 5. Save User Answer
    user_answer_entry = UserAnswer(
        id=uuid.uuid4(),
        session_id=session.session_id,
        question_id=question.id,
        user_answer=str(answer_data.user_answer), # Store the option ID they picked
        is_correct=is_correct,
        points_awarded=points_awarded
    )
    db.add(user_answer_entry)
    
    # 6. Update Session Score
    session.overall_points += points_awarded
    db.commit()
    
    # 7. Check if Test is Finished
    practice = db.query(Practice).filter(Practice.practice_id == session.practice_id).first()
    
    is_finished = False
    if practice and practice.question_ids:
        total_questions = len(practice.question_ids)
        answered_count = db.query(UserAnswer).filter(UserAnswer.session_id == session.session_id).count()
        
        if answered_count >= total_questions:
            is_finished = True
            session.is_finished = True
            db.commit()

    return {
        "message": "Answer submitted",
        "is_correct": is_correct,
        # IMPORTANT: We return the UUID string so frontend can highlight the right box
        "correct_answer": str(question.correct_answer), 
        "points_awarded": points_awarded,
        "is_test_finished": is_finished
    }


@router.get("/testing/result/{practice_id}")
def get_test_result(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id 

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


from sqlalchemy import or_, and_

@router.get("/testing/latest-assigned")
def get_latest_assigned_test(
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user)
):
    now = datetime.utcnow()
    query = (
        db.query(Practice)
        .join(PracticeAssignment, Practice.practice_id == PracticeAssignment.practice_id)
        .outerjoin(
            TestSession, 
            and_(
                TestSession.practice_id == Practice.practice_id, 
                TestSession.user_id == current_user.id
            )
        )
        .filter(
            PracticeAssignment.user_id == current_user.id,  # Assigned to this user
            Practice.is_valid == True,                      # Practice is active
            Practice.deadline > now,                        # Deadline not passed
            
            # Show if NO session exists OR session is NOT finished
            or_(TestSession.session_id == None, TestSession.is_finished == False) 
        )
        # Prioritize the one with the closest deadline
        .order_by(Practice.deadline.asc())
    )
    latest_practice = query.first()

    if not latest_practice:
        return {"message": "No pending tests found", "practice_id": None}

    return {
        "practice_id": latest_practice.practice_id,
        "title": latest_practice.title,
        "deadline": latest_practice.deadline
    }