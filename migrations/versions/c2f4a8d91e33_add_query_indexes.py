"""Add indexes for common member activity queries.

Revision ID: c2f4a8d91e33
Revises: bc41d83f6a20
Create Date: 2026-10-28 16:50:00.000000
"""

from alembic import op


revision = "c2f4a8d91e33"
down_revision = "bc41d83f6a20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_like_liker_created", "like", ["liker_id", "created_at"])
    op.create_index("ix_like_liked_created", "like", ["liked_id", "created_at"])
    op.create_index("ix_match_first_created", "match", ["first_user_id", "created_at"])
    op.create_index("ix_match_second_created", "match", ["second_user_id", "created_at"])
    op.create_index("ix_message_sender_sent", "message", ["sender_id", "sent_at"])
    op.create_index("ix_message_receiver_sent", "message", ["receiver_id", "sent_at"])
    op.create_index(
        "ix_notification_user_read_created",
        "notification",
        ["user_id", "is_read", "created_at"],
    )


def downgrade():
    op.drop_index("ix_notification_user_read_created", table_name="notification")
    op.drop_index("ix_message_receiver_sent", table_name="message")
    op.drop_index("ix_message_sender_sent", table_name="message")
    op.drop_index("ix_match_second_created", table_name="match")
    op.drop_index("ix_match_first_created", table_name="match")
    op.drop_index("ix_like_liked_created", table_name="like")
    op.drop_index("ix_like_liker_created", table_name="like")
