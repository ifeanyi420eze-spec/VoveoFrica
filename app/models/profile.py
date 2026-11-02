from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import text

from app import db


class Profile(db.Model):
    __tablename__ = "profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    location = db.Column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    user = db.relationship("User", back_populates="profile")

    __table_args__ = (
        db.Index(
            "ix_profile_location_geography",
            text("(location::geography)"),
            postgresql_using="gist",
        ),
    )


class Like(db.Model):
    """A like that one user sends to another user."""

    id = db.Column(db.Integer, primary_key=True)
    liker_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    liked_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    liker = db.relationship("User", foreign_keys=[liker_id], back_populates="likes_sent")
    liked_user = db.relationship(
        "User", foreign_keys=[liked_id], back_populates="likes_received"
    )
    __table_args__ = (
        db.Index("ix_like_liker_created", "liker_id", "created_at"),
        db.Index("ix_like_liked_created", "liked_id", "created_at"),
    )


class DailyLikeUsage(db.Model):
    """Durable count of likes sent per user and UTC calendar day."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    usage_date = db.Column(db.Date, nullable=False)
    likes_used = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("user_id", "usage_date", name="uq_user_daily_like_usage"),
    )


class Match(db.Model):
    """A match between two users."""

    id = db.Column(db.Integer, primary_key=True)
    first_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    second_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    first_user = db.relationship("User", foreign_keys=[first_user_id])
    second_user = db.relationship("User", foreign_keys=[second_user_id])
    __table_args__ = (
        db.Index("ix_match_first_created", "first_user_id", "created_at"),
        db.Index("ix_match_second_created", "second_user_id", "created_at"),
    )


class Block(db.Model):
    """A member's decision to prevent another member from contacting them."""

    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    blocker = db.relationship("User", foreign_keys=[blocker_id])
    blocked = db.relationship("User", foreign_keys=[blocked_id])

    __table_args__ = (
        db.UniqueConstraint("blocker_id", "blocked_id", name="uq_blocker_blocked"),
    )
