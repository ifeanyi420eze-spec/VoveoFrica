from datetime import datetime

from app import db


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

    profile = db.relationship(
        "Profile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
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
