import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_

# --- Imports (Ensure these match your project structure) ---
from database.database import get_db
from database.models import Practice, PracticeAssignment, Question, TestSession, UserAnswer
from routers.login import get_current_user
from schemas.user_schema import TestStatusResponse, AnswerCreate
from pydantic import BaseModel # Needed if you define models inline, but better to use schemas file

router = APIRouter()

# --- Endpoints ---

@router.post("/testing/start-test/{practice_id}")
def start_test(
    practice_id: uuid.UUID, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user)
):
    user_id = current_user.id
    
    # 1. Check Assignment
    assignment = db.query(PracticeAssignment).filter(
        PracticeAssignment.practice_id == practice_id,
        PracticeAssignment.user_id == user_id
    ).first()

    if not assignment or assignment.is_completed:
        raise HTTPException(status_code=403, detail="Test already completed or not assigned.")
    
    # 2. STRICT CHECK: Does ANY session exist (finished or unfinished)?
    existing_session = db.query(TestSession).filter(
        TestSession.user_id == user_id,
        TestSession.practice_id == practice_id
    ).first()

    if existing_session:
        # Even if it's not finished, we block re-entry
        raise HTTPException(
            status_code=403, 
            detail="You have already accessed this test. Re-entry is not allowed."
        )

    # 3. Validate Practice & Deadline
    practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
    if not practice or not practice.is_valid:
        raise HTTPException(status_code=404, detail="Practice not found")
    
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if practice.deadline and practice.deadline < now_utc:
        raise HTTPException(status_code=400, detail="Practice deadline has passed")

    # 4. Create new session
    new_session = TestSession(
        session_id=uuid.uuid4(),
        practice_id=practice_id,
        user_id=user_id,
        overall_points=0,
        is_finished=False,
        started_time=datetime.utcnow()
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {
        "message": "Test Started", 
        "session_id": new_session.session_id, 
        "quantity": len(practice.question_ids), 
        "duration": practice.duration_minutes
    }

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

    # 3. Get IDs of questions already answered (Convert to Strings for safe comparison)
    answered_uuids = db.query(UserAnswer.question_id).filter(
        UserAnswer.session_id == session.session_id
    ).all()
    answered_ids_str = [str(aid[0]) for aid in answered_uuids]

    # 4. Find the first unanswered question that ACTUALLY EXISTS
    next_question = None
    
    if practice.question_ids:
        for q_id in practice.question_ids:
            # Skip if user already answered this ID
            if str(q_id) in answered_ids_str:
                continue
            
            # Fetch the question to ensure it exists in DB
            question_obj = db.query(Question).filter(Question.id == q_id).first()
            if question_obj:
                next_question = question_obj
                break
            else:
                # If ID is in Practice but not in Questions table, we skip it (Fixes 500 error)
                print(f"Warning: Question ID {q_id} not found in DB. Skipping.")
    
    # If no valid questions left, finish the test
    if not next_question:
        session.is_finished = True
        db.commit()
        return {"message": "Test Finished", "is_finished": True}

    return {
        "id": next_question.id,
        "text": next_question.text,
        "options": next_question.options,
        "category": next_question.category,
        "points": next_question.points
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

    # 4. Check Logic (Normalized Scoring)
    # Calculate Total Weight of this specific practice for 100% score scaling
    practice = db.query(Practice).filter(Practice.practice_id == session.practice_id).first()
    total_weight = 0
    if practice.question_ids:
        # Sum points of all questions in this practice
        total_weight = db.query(func.sum(Question.points))\
            .filter(Question.id.in_(practice.question_ids))\
            .scalar() or 1  # Avoid division by zero

    is_correct = str(question.correct_answer) == str(answer_data.user_answer)
    
    # Calculate normalized points (If correct, give portion of 100)
    points_awarded = 0.0
    if is_correct:
        points_awarded = (question.points / total_weight) * 100

    # 5. Save User Answer
    user_answer_entry = UserAnswer(
        id=uuid.uuid4(),
        session_id=session.session_id,
        question_id=question.id,
        user_answer=str(answer_data.user_answer),
        is_correct=is_correct,
        points_awarded=points_awarded
    )
    db.add(user_answer_entry)
    
    # 6. Update Session Score
    session.overall_points += points_awarded
    db.commit()
    
    # 7. Check if Test is Finished
    is_finished = False
# Inside your submit_answer function, near the bottom:
    if practice and practice.question_ids:
        answered_count = db.query(UserAnswer).filter(UserAnswer.session_id == session.session_id).count()
        
        if answered_count >= len(practice.question_ids):
            is_finished = True
            session.is_finished = True
            
            # Update assignment status automatically
            assignment = db.query(PracticeAssignment).filter(
                PracticeAssignment.practice_id == session.practice_id,
                PracticeAssignment.user_id == user_id
            ).first()
            if assignment:
                assignment.is_completed = True
                assignment.completed_at = datetime.utcnow()
            
            db.commit()
    return {
        "message": "Answer submitted",
        "is_correct": is_correct,
        "correct_answer": str(question.correct_answer), 
        "points_awarded": round(points_awarded, 2),
        "is_test_finished": is_finished
    }


@router.get("/testing/result/{practice_id}")
def get_test_result(
    practice_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user_id = current_user.id 

    session = db.query(TestSession).filter(
        TestSession.user_id == user_id,
        TestSession.practice_id == practice_id
    ).order_by(TestSession.started_time.desc()).first()

    if not session:
        raise HTTPException(status_code=404, detail="No session found")

    return {
        "practice_id": practice_id,
        "total_score": round(session.overall_points, 2),
        "is_finished": session.is_finished,
        "started_at": session.started_time
    }

@router.get("/testing/assigned/{filter_option}")
def get_assigned_tests(
    filter_option: str, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user)
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # Updated Query: Join Practice with Assignment
    # We filter out any practice that already has a TestSession entry
    query = (
        db.query(Practice)
        .join(PracticeAssignment, Practice.practice_id == PracticeAssignment.practice_id)
        .outerjoin(TestSession, and_(
            TestSession.practice_id == Practice.practice_id,
            TestSession.user_id == current_user.id
        ))
        .filter(
            PracticeAssignment.user_id == current_user.id,
            Practice.is_valid == True,
            Practice.deadline > now,
            PracticeAssignment.is_completed == False, # Hide completed assignments
            TestSession.session_id == None            # Hide if a session was EVER started
        )
        .order_by(Practice.deadline.asc())
    )

    def format_assessment(p: Practice):
        return {
            "practiceId": str(p.practice_id),
            "title": p.title,
            "type": "pending", # Since we filter active/completed out, all will be pending
            "dueDate": p.deadline.isoformat() if p.deadline else None,
            "duration": f"{p.duration_minutes} min",
            "questionQuantity": len(p.question_ids) if p.question_ids else 0
        }

    practices = query.all()
    results = [format_assessment(p) for p in practices]

    # ... keep your existing 'latest', 'all', and limit logic ...
    if filter_option == "latest":
        return results[0] if results else None
    elif filter_option == "all":
        return results
    else:
        try:
            limit = int(filter_option)
            return results[:limit]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid filter option.")
                

@router.post("/testing/finish-test/{session_id}")
def finish_test(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 1. Fetch the session
    session = db.query(TestSession).filter(
        TestSession.session_id == session_id,
        TestSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Test session not found.")

    if session.is_finished:
        return {"message": "Test was already finished", "final_score": round(session.overall_points, 2)}

    # 2. Mark session as finished
    session.is_finished = True
    
    # 3. Mark the Assignment as officially done
    assignment = db.query(PracticeAssignment).filter(
        PracticeAssignment.practice_id == session.practice_id,
        PracticeAssignment.user_id == current_user.id
    ).first()
    
    if assignment:
        assignment.is_completed = True
        assignment.completed_at = datetime.utcnow()

    db.commit()

    # 4. Return summary
    practice = db.query(Practice).filter(Practice.practice_id == session.practice_id).first()
    answered_count = db.query(UserAnswer).filter(UserAnswer.session_id == session_id).count()
    total_questions = len(practice.question_ids) if practice and practice.question_ids else 0

    return {
        "message": "Assignment completed and locked.",
        "final_score": round(session.overall_points, 2),
        "completion_stats": f"{answered_count}/{total_questions} answered",
        "completed_at": assignment.completed_at if assignment else None
    }