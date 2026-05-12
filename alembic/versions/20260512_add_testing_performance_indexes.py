"""Add testing performance indexes

Revision ID: 20260512idx
Revises: 81a408e504ad
Create Date: 2026-05-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260512idx"
down_revision: Union[str, Sequence[str], None] = "81a408e504ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_users_company_id", "users", ["company_id"])
    op.create_index("ix_created_vacancies_company_id", "created_vacancies", ["company_id"])
    op.create_index("ix_candidates_user_id", "candidates", ["user_id"])
    op.create_index("ix_candidates_vacancy_id", "candidates", ["vacancy_id"])
    op.create_index("ix_question_history_question_id", "question_history", ["question_id"])
    op.create_index("ix_question_history_changed_by", "question_history", ["changed_by"])
    op.create_index("ix_user_questions_category", "user_questions", ["category"])

    op.create_index("ix_practice_assignments_practice_id", "practice_assignments", ["practice_id"])
    op.create_index("ix_practice_assignments_user_id", "practice_assignments", ["user_id"])
    op.create_index(
        "ix_practice_assignments_practice_user",
        "practice_assignments",
        ["practice_id", "user_id"],
    )

    op.create_index("ix_test_session_practice_id", "test_session", ["practice_id"])
    op.create_index("ix_test_session_user_id", "test_session", ["user_id"])
    op.create_index(
        "ix_test_session_user_practice",
        "test_session",
        ["user_id", "practice_id"],
    )
    op.create_index(
        "ix_test_session_user_finished_started",
        "test_session",
        ["user_id", "is_finished", "started_time"],
    )

    op.create_index("ix_user_answers_session_id", "user_answers", ["session_id"])
    op.create_index("ix_user_answers_question_id", "user_answers", ["question_id"])
    op.create_index(
        "ix_user_answers_session_question",
        "user_answers",
        ["session_id", "question_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_user_answers_session_question", table_name="user_answers")
    op.drop_index("ix_user_answers_question_id", table_name="user_answers")
    op.drop_index("ix_user_answers_session_id", table_name="user_answers")

    op.drop_index("ix_test_session_user_finished_started", table_name="test_session")
    op.drop_index("ix_test_session_user_practice", table_name="test_session")
    op.drop_index("ix_test_session_user_id", table_name="test_session")
    op.drop_index("ix_test_session_practice_id", table_name="test_session")

    op.drop_index("ix_practice_assignments_practice_user", table_name="practice_assignments")
    op.drop_index("ix_practice_assignments_user_id", table_name="practice_assignments")
    op.drop_index("ix_practice_assignments_practice_id", table_name="practice_assignments")

    op.drop_index("ix_user_questions_category", table_name="user_questions")
    op.drop_index("ix_question_history_changed_by", table_name="question_history")
    op.drop_index("ix_question_history_question_id", table_name="question_history")
    op.drop_index("ix_candidates_vacancy_id", table_name="candidates")
    op.drop_index("ix_candidates_user_id", table_name="candidates")
    op.drop_index("ix_created_vacancies_company_id", table_name="created_vacancies")
    op.drop_index("ix_users_company_id", table_name="users")
