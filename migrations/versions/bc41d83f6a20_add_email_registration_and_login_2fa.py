"""Add email verification and login two-factor challenges.

Revision ID: bc41d83f6a20
Revises: 91d4be70c215
Create Date: 2026-10-27 15:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "bc41d83f6a20"
down_revision = "91d4be70c215"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "email_auth_challenge",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_email_auth_challenge_user_id",
        "email_auth_challenge",
        ["user_id"],
    )


def downgrade():
    op.drop_index("ix_email_auth_challenge_user_id", table_name="email_auth_challenge")
    op.drop_table("email_auth_challenge")
    op.drop_column("user", "email_verified")
