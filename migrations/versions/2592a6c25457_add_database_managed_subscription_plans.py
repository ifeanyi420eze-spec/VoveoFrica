"""Add database-managed subscription plans

Revision ID: 2592a6c25457
Revises: 08976d46d73a
Create Date: 2026-10-26 16:05:07.269858

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2592a6c25457'
down_revision = '08976d46d73a'
branch_labels = None
depends_on = None


def upgrade():
    # Create a catalog so the public plans page reads prices from MySQL.
    op.create_table('subscription_plan',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('duration_days', sa.Integer(), nullable=False),
    sa.Column('amount_ngn', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('is_featured', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )

    plans = sa.table(
        'subscription_plan',
        sa.column('name', sa.String),
        sa.column('duration_days', sa.Integer),
        sa.column('amount_ngn', sa.Numeric(10, 2)),
        sa.column('description', sa.String),
        sa.column('is_featured', sa.Boolean),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(
        plans,
        [
            {'name': 'Daily', 'duration_days': 1, 'amount_ngn': 300, 'description': 'A little time to explore.', 'is_featured': False, 'is_active': True},
            {'name': 'Weekly', 'duration_days': 7, 'amount_ngn': 1000, 'description': 'Start making new connections.', 'is_featured': False, 'is_active': True},
            {'name': 'Biweekly', 'duration_days': 14, 'amount_ngn': 1500, 'description': 'Give good conversations more time.', 'is_featured': False, 'is_active': True},
            {'name': 'Monthly', 'duration_days': 30, 'amount_ngn': 2500, 'description': 'A full month to find your rhythm.', 'is_featured': True, 'is_active': True},
            {'name': '3 months', 'duration_days': 90, 'amount_ngn': 6000, 'description': 'More time for something meaningful.', 'is_featured': False, 'is_active': True},
            {'name': '6 months', 'duration_days': 180, 'amount_ngn': 10000, 'description': 'Settle in and see where it leads.', 'is_featured': False, 'is_active': True},
            {'name': 'Yearly', 'duration_days': 365, 'amount_ngn': 15000, 'description': 'Your whole year of new possibilities.', 'is_featured': False, 'is_active': True},
        ],
    )


def downgrade():
    op.drop_table('subscription_plan')
