"""Add candidate portal profile, certificates, and resume reviews

Revision ID: 20260521portal
Revises: 81a408e504ad
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260521portal"
down_revision: Union[str, Sequence[str], None] = "81a408e504ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("headline", sa.String(length=150), nullable=True),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("university", sa.String(length=150), nullable=True),
        sa.Column("graduation_year", sa.String(length=10), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("portfolio_url", sa.String(length=255), nullable=True),
        sa.Column("linkedin_url", sa.String(length=255), nullable=True),
        sa.Column("open_to_work", sa.Boolean(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_candidate_profiles_user_id", "candidate_profiles", ["user_id"])

    op.create_table(
        "candidate_certificates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("provider", sa.String(length=150), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("credential_id", sa.String(length=80), nullable=True),
        sa.Column("badge_label", sa.String(length=60), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("file_url", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=255), nullable=True),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
    )
    op.create_index("ix_candidate_certificates_user_id", "candidate_certificates", ["user_id"])
    op.create_index(
        "ix_candidate_certificates_user_status",
        "candidate_certificates",
        ["user_id", "status"],
    )

    op.create_table(
        "candidate_resume_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_url", sa.String(length=255), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("analysis_summary", sa.Text(), nullable=True),
        sa.Column("strengths", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("suggestions", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidate_resume_reviews_user_id", "candidate_resume_reviews", ["user_id"])
    op.create_index(
        "ix_candidate_resume_reviews_user_created",
        "candidate_resume_reviews",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_candidate_resume_reviews_user_created", table_name="candidate_resume_reviews")
    op.drop_index("ix_candidate_resume_reviews_user_id", table_name="candidate_resume_reviews")
    op.drop_table("candidate_resume_reviews")

    op.drop_index("ix_candidate_certificates_user_status", table_name="candidate_certificates")
    op.drop_index("ix_candidate_certificates_user_id", table_name="candidate_certificates")
    op.drop_table("candidate_certificates")

    op.drop_index("ix_candidate_profiles_user_id", table_name="candidate_profiles")
    op.drop_table("candidate_profiles")
