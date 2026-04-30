import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import Integer, func, or_, and_

# --- Imports (Ensure these match your project structure) ---
from database.database import get_db
from database.models import Practice, PracticeAssignment, Question, TestSession, UserAnswer
from routers.login import get_current_user, get_current_user_from_token # Assumes you have the decoder here
from schemas.user_schema import TestStatusResponse, AnswerCreate
from utils.ai_logic import calculate_difficulty_score

router = APIRouter(prefix="/testing", tags=["Testing"])

# --- WebSocket Auth Dependency ---
async def get_current_user_ws(
    websocket: WebSocket, 
    token: str = Query(...), 
    db: Session = Depends(get_db)
):
    """Authenticates the WebSocket connection via query parameter token."""
    user = get_current_user_from_token(token, db)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    return user

# --- Helper Logic ---
async def handle_finish_test(session_id: uuid.UUID, user_id: uuid.UUID, practice_id: uuid.UUID, db: Session, websocket: WebSocket):
    """Helper function to lock the test and assignment cleanly."""
    session = db.query(TestSession).filter(TestSession.session_id == session_id).first()
    
    if session and not session.is_finished:
        session.is_finished = True
        
        assignment = db.query(PracticeAssignment).filter(
            PracticeAssignment.practice_id == practice_id,
            PracticeAssignment.user_id == user_id
        ).first()
        
        if assignment:
            assignment.is_completed = True
            assignment.completed_at = datetime.utcnow()
            
        db.commit()

        await websocket.send_json({
            "event": "test_finished",
            "final_score": round(session.overall_points, 2),
            "message": "Assignment completed and locked."
        })
        await websocket.close()


# ==========================================
# 1. LIVE TESTING WEBSOCKET (The Core Loop)
# ==========================================

@router.websocket("/practices/{practice_id}/ws")
async def testing_websocket(
    websocket: WebSocket, 
    practice_id: uuid.UUID, 
    current_user = Depends(get_current_user_ws),
    db: Session = Depends(get_db)
):
    if not current_user:
        return # Auth failed, connection already closed in dependency

    await websocket.accept()
    user_id = current_user.id
    session_id = None # Tracks the active session for this connection

    try:
        while True:
            # Wait for the frontend to send an action
            data = await websocket.receive_json()
            action = data.get("action")

            # --- ACTION: START TEST ---
            if action == "start_test":
                assignment = db.query(PracticeAssignment).filter(
                    PracticeAssignment.practice_id == practice_id,
                    PracticeAssignment.user_id == user_id
                ).first()

                if not assignment or assignment.is_completed:
                    await websocket.send_json({"error": "Test already completed or not assigned."})
                    continue

                existing_session = db.query(TestSession).filter(
                    TestSession.user_id == user_id,
                    TestSession.practice_id == practice_id
                ).first()

                if existing_session:
                    await websocket.send_json({"error": "Re-entry is not allowed."})
                    await websocket.close()
                    return

                practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
                if not practice or not practice.is_valid:
                    await websocket.send_json({"error": "Practice not found."})
                    continue

                now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                if practice.deadline and practice.deadline < now_utc:
                    await websocket.send_json({"error": "Practice deadline has passed."})
                    await websocket.close()
                    return

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
                
                session_id = new_session.session_id

                await websocket.send_json({
                    "event": "test_started",
                    "session_id": str(session_id),
                    "quantity": len(practice.question_ids) if practice.question_ids else 0,
                    "duration": practice.duration_minutes
                })

            # --- ACTION: GET QUESTION ---
            elif action == "get_question":
                if not session_id:
                    await websocket.send_json({"error": "Test not started."})
                    continue

                practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
                answered_uuids = db.query(UserAnswer.question_id).filter(UserAnswer.session_id == session_id).all()
                answered_ids_str = [str(aid[0]) for aid in answered_uuids]

                next_question = None
                if practice and practice.question_ids:
                    for q_id in practice.question_ids:
                        if str(q_id) in answered_ids_str:
                            continue
                        
                        question_obj = db.query(Question).filter(Question.id == q_id).first()
                        if question_obj:
                            next_question = question_obj
                            break

                if not next_question:
                    await handle_finish_test(session_id, user_id, practice_id, db, websocket)
                else:
                    await websocket.send_json({
                        "event": "question_data",
                        "id": str(next_question.id),
                        "text": next_question.text,
                        "options": next_question.options,
                        "category": next_question.category,
                        "points": next_question.points
                    })

            # --- ACTION: SUBMIT ANSWER ---
            elif action == "submit_answer":
                if not session_id:
                    await websocket.send_json({"error": "Test not started."})
                    continue

                q_id = data.get("question_id")
                user_ans = str(data.get("user_answer"))
                time_spent = data.get("time_spent", 0)

                question = db.query(Question).filter(Question.id == q_id).first()
                if not question:
                    await websocket.send_json({"error": "Question not found."})
                    continue

                existing_answer = db.query(UserAnswer).filter(
                    UserAnswer.session_id == session_id,
                    UserAnswer.question_id == question.id
                ).first()

                if existing_answer:
                    await websocket.send_json({"error": "Question already answered."})
                    continue

                practice = db.query(Practice).filter(Practice.practice_id == practice_id).first()
                total_weight = 1
                if practice.question_ids:
                    total_weight = db.query(func.sum(Question.points))\
                        .filter(Question.id.in_(practice.question_ids)).scalar() or 1 

                is_correct = str(question.correct_answer) == user_ans
                points_awarded = (question.points / total_weight) * 100 if is_correct else 0.0

                user_answer_entry = UserAnswer(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    question_id=question.id,
                    user_answer=user_ans,
                    is_correct=is_correct,
                    points_awarded=points_awarded,
                    time_spent=time_spent
                )
                db.add(user_answer_entry)
                db.flush() 

                session = db.query(TestSession).filter(TestSession.session_id == session_id).first()
                session.overall_points += points_awarded

                # AI Difficulty logic
                stats = db.query(
                    func.count(UserAnswer.id).label("total"),
                    func.sum(func.cast(UserAnswer.is_correct == False, Integer)).label("failures"),
                    func.avg(UserAnswer.time_spent).label("avg_time")
                ).filter(UserAnswer.question_id == question.id).first()

                if stats.total > 0:
                    f_rate = (stats.failures or 0) / stats.total
                    t_factor = float(stats.avg_time or 0)
                    question.difficulty_level = calculate_difficulty_score(f_rate, t_factor)

                db.commit()

                # Check if finished
                answered_count = db.query(UserAnswer).filter(UserAnswer.session_id == session_id).count()
                if answered_count >= len(practice.question_ids):
                    # Trigger clean finish
                    await handle_finish_test(session_id, user_id, practice_id, db, websocket)
                else:
                    await websocket.send_json({
                        "event": "answer_result",
                        "is_correct": is_correct,
                        "correct_answer": str(question.correct_answer),
                        "points_awarded": round(points_awarded, 2),
                        "new_difficulty": question.difficulty_level
                    })

            # --- ACTION: FINISH TEST (Manual) ---
            elif action == "finish_test":
                if session_id:
                    await handle_finish_test(session_id, user_id, practice_id, db, websocket)

    except WebSocketDisconnect:
        # Standard safety cleanup if the user closes their browser suddenly
        print(f"User {user_id} disconnected from session {session_id}")
        db.rollback()


# ==========================================
# 2. DASHBOARD / DATA REST API ENDPOINTS
# ==========================================

@router.get("/practices/{practice_id}/result")
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

@router.get("/assignments/{filter_option}")
def get_assigned_tests(
    filter_option: str, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user)
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
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
            PracticeAssignment.is_completed == False, 
            TestSession.session_id == None            
        )
        .order_by(Practice.deadline.asc())
    )

    def format_assessment(p: Practice):
        return {
            "practiceId": str(p.practice_id),
            "title": p.title,
            "type": "pending", 
            "dueDate": p.deadline.isoformat() if p.deadline else None,
            "duration": f"{p.duration_minutes} min",
            "questionQuantity": len(p.question_ids) if p.question_ids else 0
        }

    practices = query.all()
    results = [format_assessment(p) for p in practices]

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
