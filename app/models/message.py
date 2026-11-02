from datetime import datetime

from app import db


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
