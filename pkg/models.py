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
    bio = db.Column(db.Text, default="")
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


class Match(db.Model):
    """A match between two users."""

    id = db.Column(db.Integer, primary_key=True)
    first_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    second_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    first_user = db.relationship("User", foreign_keys=[first_user_id])
    second_user = db.relationship("User", foreign_keys=[second_user_id])


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


class Notification(db.Model):
    """A notification that appears for a user."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", backref="notifications")
