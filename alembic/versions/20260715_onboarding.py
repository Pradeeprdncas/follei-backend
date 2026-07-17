"""Baseline marker for the existing local schema.

The original source migrations were absent from this checkout while the live
schema is already stamped at this revision.  This no-op marker lets Alembic
continue from that known, non-destructive baseline.
"""
revision = "20260715_onboarding"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
