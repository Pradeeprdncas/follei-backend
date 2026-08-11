"""Add one-use passwordless authentication challenges.

Revision ID: 20260813_passwordless_otp
Revises: 20260812_google_context
"""
from alembic import op
import sqlalchemy as sa


revision = "20260813_passwordless_otp"
down_revision = "20260812_google_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_otp_challenges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_auth_otp_challenges_email_hash", "auth_otp_challenges", ["email_hash"])
    op.create_index("ix_auth_otp_challenges_user_id", "auth_otp_challenges", ["user_id"])
    op.create_index("ix_auth_otp_challenges_expires_at", "auth_otp_challenges", ["expires_at"])
    op.create_index("ix_auth_otp_challenges_created_at", "auth_otp_challenges", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_otp_challenges_created_at", table_name="auth_otp_challenges")
    op.drop_index("ix_auth_otp_challenges_expires_at", table_name="auth_otp_challenges")
    op.drop_index("ix_auth_otp_challenges_user_id", table_name="auth_otp_challenges")
    op.drop_index("ix_auth_otp_challenges_email_hash", table_name="auth_otp_challenges")
    op.drop_table("auth_otp_challenges")
