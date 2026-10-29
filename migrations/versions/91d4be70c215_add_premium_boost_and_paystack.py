"""Add one-time Premium and Boost purchases with Paystack references.

Revision ID: 91d4be70c215
Revises: 6a2f51d3c840
Create Date: 2026-10-27 12:05:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "91d4be70c215"
down_revision = "6a2f51d3c840"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "daily_like_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("likes_used", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "usage_date", name="uq_user_daily_like_usage"),
    )
    op.add_column(
        "subscription_plan",
        sa.Column("plan_type", sa.String(length=20), nullable=False, server_default="premium"),
    )
    op.add_column(
        "subscription",
        sa.Column("plan_type", sa.String(length=20), nullable=False, server_default="premium"),
    )
    op.add_column("subscription", sa.Column("payment_provider", sa.String(length=30), nullable=True))
    op.add_column("subscription", sa.Column("payment_reference", sa.String(length=100), nullable=True))
    op.add_column("subscription", sa.Column("payment_email", sa.String(length=120), nullable=True))
    op.add_column("subscription", sa.Column("paid_at", sa.DateTime(), nullable=True))
    op.create_unique_constraint(
        "uq_subscription_payment_reference",
        "subscription",
        ["payment_reference"],
    )
    plans = sa.table(
        "subscription_plan",
        sa.column("name", sa.String),
        sa.column("duration_days", sa.Integer),
        sa.column("amount_ngn", sa.Numeric(10, 2)),
        sa.column("description", sa.String),
        sa.column("is_featured", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("plan_type", sa.String),
    )
    op.execute(
        plans.update()
        .where(plans.c.name == "Daily")
        .values(description="A one-day Premium pass. Pay once; it never auto-renews.")
    )
    op.execute(
        plans.update()
        .where(plans.c.name == "Weekly")
        .values(description="Seven days of Premium access. A flexible, one-time pass.")
    )
    op.execute(
        plans.update()
        .where(plans.c.name == "Biweekly")
        .values(description="Fourteen days of Premium access. Pay once; no automatic renewal.")
    )
    op.execute(
        plans.update()
        .where(plans.c.name == "Monthly")
        .values(description="Thirty days of Premium access. Pay once; no automatic renewal.")
    )
    op.execute(
        plans.update()
        .where(plans.c.name == "3 months")
        .values(description="Ninety days of Premium access, equivalent to ₦2,000 per month.")
    )
    op.execute(
        plans.update()
        .where(plans.c.name == "6 months")
        .values(description="One hundred and eighty days of Premium access, equivalent to about ₦1,667 per month.")
    )
    op.execute(
        plans.update()
        .where(plans.c.name == "Yearly")
        .values(description="Three hundred and sixty-five days of Premium access, equivalent to ₦1,250 per month.")
    )
    op.bulk_insert(
        plans,
        [
            {
                "name": "24-hour Boost",
                "duration_days": 1,
                "amount_ngn": 500,
                "description": "A one-time 24-hour profile boost for ₦500. No subscription required.",
                "is_featured": False,
                "is_active": True,
                "plan_type": "boost",
            }
        ],
    )


def downgrade():
    op.drop_constraint(
        "uq_subscription_payment_reference",
        "subscription",
        type_="unique",
    )
    op.drop_column("subscription", "paid_at")
    op.drop_column("subscription", "payment_email")
    op.drop_column("subscription", "payment_reference")
    op.drop_column("subscription", "payment_provider")
    op.drop_column("subscription", "plan_type")
    op.drop_column("subscription_plan", "plan_type")
    op.drop_table("daily_like_usage")
