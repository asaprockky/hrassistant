"""Add AI interview tables

Revision ID: 20260522aiinterview
Revises: 20260521portal
Create Date: 2026-05-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260522aiinterview"
down_revision: Union[str, Sequence[str], None] = "20260521portal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_interview_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("final_feedback", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_interview_sessions_user_id",
        "ai_interview_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_interview_sessions_user",
        "ai_interview_sessions",
        ["user_id", "status"],
    )

    op.create_table(
        "ai_interview_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["session_id"], ["ai_interview_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_interview_messages_session_created",
        "ai_interview_messages",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_interview_messages_session_created", table_name="ai_interview_messages")
    op.drop_table("ai_interview_messages")
    op.drop_index("ix_ai_interview_sessions_user", table_name="ai_interview_sessions")
    op.drop_index("ix_ai_interview_sessions_user_id", table_name="ai_interview_sessions")
    op.drop_table("ai_interview_sessions")
