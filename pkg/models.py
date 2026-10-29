from datetime import datetime

from pkg import db


class User(db.Model):
    """A person who has registered for the dating app."""

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(30), nullable=False)
    country = db.Column(db.String(80), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    town = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email_verified = db.Column(db.Boolean, nullable=False, default=True)
    bio = db.Column(db.Text, default="")
    profile_photo = db.Column(db.String(255))
    interests = db.Column(db.String(500), default="")
    profile_prompt = db.Column(db.String(120), default="")
    profile_answer = db.Column(db.String(280), default="")
    relationship_goal = db.Column(db.String(40), default="")
    preferred_goals = db.Column(db.String(240), default="")
    preferred_interests = db.Column(db.String(500), default="")
    preferred_country = db.Column(db.String(80), default="")
    preferred_city = db.Column(db.String(80), default="")
    verification_status = db.Column(db.String(20), nullable=False, default="unverified")
    verification_requested_at = db.Column(db.DateTime)
    verification_reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    likes_sent = db.relationship(
        "Like",
        foreign_keys="Like.liker_id",
        back_populates="liker",
        cascade="all, delete-orphan",
    )
    likes_received = db.relationship(
        "Like",
        foreign_keys="Like.liked_id",
        back_populates="liked_user",
        cascade="all, delete-orphan",
    )
    messages_sent = db.relationship(
        "Message",
        foreign_keys="Message.sender_id",
        back_populates="sender",
        cascade="all, delete-orphan",
    )
    messages_received = db.relationship(
        "Message",
        foreign_keys="Message.receiver_id",
        back_populates="receiver",
        cascade="all, delete-orphan",
    )
    subscriptions = db.relationship(
        "Subscription",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Subscription(db.Model):
    """A user's selected plan, price, and subscription period."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    plan_name = db.Column(db.String(50), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    amount_ngn = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    plan_type = db.Column(db.String(20), nullable=False, default="premium")
    payment_provider = db.Column(db.String(30))
    payment_reference = db.Column(db.String(100), unique=True)
    payment_email = db.Column(db.String(120))
    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="subscriptions")


class SubscriptionPlan(db.Model):
    """A purchasable subscription plan shown on the public plans page."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    duration_days = db.Column(db.Integer, nullable=False)
    amount_ngn = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    plan_type = db.Column(db.String(20), nullable=False, default="premium")
    is_featured = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


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


class Message(db.Model):
    """A message sent between two users."""

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    sender = db.relationship(
        "User", foreign_keys=[sender_id], back_populates="messages_sent"
    )
    receiver = db.relationship(
        "User", foreign_keys=[receiver_id], back_populates="messages_received"
    )
    __table_args__ = (
        db.Index("ix_message_sender_sent", "sender_id", "sent_at"),
        db.Index("ix_message_receiver_sent", "receiver_id", "sent_at"),
    )


class Report(db.Model):
    """A report that a user submits about another user."""

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reported_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reason = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_reviewed = db.Column(db.Boolean, default=False, nullable=False)

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    reported_user = db.relationship("User", foreign_keys=[reported_user_id])


class EmailAuthChallenge(db.Model):
    """A short-lived one-time email code for registration or login."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    purpose = db.Column(db.String(20), nullable=False)
    code_digest = db.Column(db.String(64), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime)

    user = db.relationship("User")


class Notification(db.Model):
    """A notification that appears for a user."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(30), nullable=False, default="activity")
    link_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", backref="notifications")
    __table_args__ = (
        db.Index("ix_notification_user_read_created", "user_id", "is_read", "created_at"),
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
