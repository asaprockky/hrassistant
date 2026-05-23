"""Student portal hardening

Revision ID: 20260523_student_portal_hardening
Revises: 81a408e504ad
Create Date: 2026-05-23
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260523_student_portal_hardening"
down_revision: Union[str, Sequence[str], None] = "81a408e504ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE candidate_profiles
        ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(255);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_notification_state (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            last_read_at TIMESTAMP NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS candidate_notification_state;")
    op.execute("ALTER TABLE candidate_profiles DROP COLUMN IF EXISTS avatar_url;")
