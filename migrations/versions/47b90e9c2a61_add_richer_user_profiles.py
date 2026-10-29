"""Add profile photos, interests, and prompts to users.

Revision ID: 47b90e9c2a61
Revises: 2592a6c25457
Create Date: 2026-10-27 10:50:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "47b90e9c2a61"
down_revision = "2592a6c25457"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("profile_photo", sa.String(length=255)))
    op.add_column("user", sa.Column("interests", sa.String(length=500), nullable=True))
    op.add_column("user", sa.Column("profile_prompt", sa.String(length=120), nullable=True))
    op.add_column("user", sa.Column("profile_answer", sa.String(length=280), nullable=True))


def downgrade():
    op.drop_column("user", "profile_answer")
    op.drop_column("user", "profile_prompt")
    op.drop_column("user", "interests")
    op.drop_column("user", "profile_photo")
