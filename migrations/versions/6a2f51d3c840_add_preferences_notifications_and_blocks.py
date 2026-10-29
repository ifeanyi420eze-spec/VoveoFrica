"""Add discovery preferences, notification links, and blocks.

Revision ID: 6a2f51d3c840
Revises: 47b90e9c2a61
Create Date: 2026-10-27 11:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "6a2f51d3c840"
down_revision = "47b90e9c2a61"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("relationship_goal", sa.String(length=40), nullable=True))
    op.add_column("user", sa.Column("preferred_goals", sa.String(length=240), nullable=True))
    op.add_column("user", sa.Column("preferred_interests", sa.String(length=500), nullable=True))
    op.add_column("user", sa.Column("preferred_country", sa.String(length=80), nullable=True))
    op.add_column("user", sa.Column("preferred_city", sa.String(length=80), nullable=True))
    op.add_column(
        "user",
        sa.Column("verification_status", sa.String(length=20), nullable=False, server_default="unverified"),
    )
    op.add_column("user", sa.Column("verification_requested_at", sa.DateTime(), nullable=True))
    op.add_column("user", sa.Column("verification_reviewed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "notification",
        sa.Column("category", sa.String(length=30), nullable=False, server_default="activity"),
    )
    op.add_column("notification", sa.Column("link_url", sa.String(length=255), nullable=True))
    op.create_table(
        "block",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blocker_id", sa.Integer(), nullable=False),
        sa.Column("blocked_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["blocker_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["blocked_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_blocker_blocked"),
    )


def downgrade():
    op.drop_table("block")
    op.drop_column("notification", "link_url")
    op.drop_column("notification", "category")
    op.drop_column("user", "preferred_city")
    op.drop_column("user", "preferred_country")
    op.drop_column("user", "preferred_interests")
    op.drop_column("user", "preferred_goals")
    op.drop_column("user", "verification_reviewed_at")
    op.drop_column("user", "verification_requested_at")
    op.drop_column("user", "verification_status")
    op.drop_column("user", "relationship_goal")
