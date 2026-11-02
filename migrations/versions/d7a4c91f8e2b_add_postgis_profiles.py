"""Add PostGIS profile locations.

Revision ID: d7a4c91f8e2b
Revises: c2f4a8d91e33
Create Date: 2026-11-02 13:45:00.000000
"""

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry


revision = "d7a4c91f8e2b"
down_revision = "c2f4a8d91e33"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "location",
            Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.execute(
        "CREATE INDEX ix_profile_location_geography "
        "ON profiles USING GIST ((location::geography))"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_profile_location_geography")
    op.drop_table("profiles")
