import re
from datetime import datetime, timedelta

from flask import Blueprint, current_app, request, url_for
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app import db, limiter
from app.models import Block, Match, Message, Notification, User
from app.routes.auth import get_authenticated_user
from app.services.realtime import (
    RealtimeDeliveryError,
    authorize_channel,
    broadcast_event,
    broadcast_message,
)
from app.services.content_moderation import contains_profanity


chat_bp = Blueprint("chat", __name__)
CHAT_MESSAGES_PER_MINUTE = 30


def _conversation_allowed(user_id, other_user_id):
    if other_user_id == user_id:
        return False
    low_id, high_id = sorted((user_id, other_user_id))
    matched = Match.query.filter_by(
        first_user_id=low_id,
        second_user_id=high_id,
    ).first()
    blocked = Block.query.filter(
        or_(
            (Block.blocker_id == user_id) & (Block.blocked_id == other_user_id),
            (Block.blocker_id == other_user_id) & (Block.blocked_id == user_id),
        )
    ).first()
    return matched is not None and blocked is None


def _request_other_user(data):
    if not isinstance(data, dict):
        return None, ({"ok": False, "error": "Invalid conversation."}, 400)
    user = get_authenticated_user()
    if user is None:
        return None, ({"ok": False, "error": "You must be logged in to chat."}, 401)
    try:
        other_user_id = int(data.get("other_user_id"))
    except (TypeError, ValueError):
        return None, ({"ok": False, "error": "Invalid conversation."}, 400)
    other_user = db.session.get(User, other_user_id)
    if other_user is None or not _conversation_allowed(user.id, other_user.id):
        return None, ({"ok": False, "error": "You cannot access this conversation."}, 403)
    return (user, other_user), None


@chat_bp.post("/pusher/auth")
def authorize_pusher_channel():
    user = get_authenticated_user()
    data = request.form
    channel_name = data.get("channel_name", "")
    socket_id = data.get("socket_id", "")
    if user is None:
        return {"error": "You must be logged in to chat."}, 401
    if (
        len(channel_name) > 128
        or not channel_name.startswith("private-chat-")
        or not re.fullmatch(r"\d{1,20}\.\d{1,20}", socket_id)
    ):
        return {"error": "Invalid private conversation channel."}, 400
    parts = channel_name.removeprefix("private-chat-").split("-")
    if (
        len(parts) != 2
        or not all(part.isdigit() and len(part) <= 10 for part in parts)
    ):
        return {"error": "Invalid private conversation channel."}, 400
    first_id, second_id = map(int, parts)
    expected_channel = (
        f"private-chat-{min(first_id, second_id)}-{max(first_id, second_id)}"
    )
    if (
        user.id not in (first_id, second_id)
        or channel_name != expected_channel
        or not _conversation_allowed(first_id, second_id)
    ):
        return {"error": "You cannot join this conversation."}, 403
    try:
        auth_data = authorize_channel(channel_name, socket_id)
    except RealtimeDeliveryError:
        return {"error": "Real-time chat is temporarily unavailable."}, 503
    return auth_data, 200


@chat_bp.post("/send")
def send_chat_message():
    user = get_authenticated_user()
    if user is None:
        return {"ok": False, "error": "You must be logged in to send messages."}, 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"ok": False, "error": "Invalid message."}, 400
    try:
        other_user_id = int(data.get("other_user_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid conversation."}, 400

    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "error": "Please enter a message."}, 400
    text = text.strip()
    if len(text) > 5000:
        return {"ok": False, "error": "Messages cannot be longer than 5000 characters."}, 400
    if contains_profanity(text):
        return {
            "ok": False,
            "error": "Please keep messages respectful. This message contains language that cannot be sent.",
        }, 400
    if Message.query.filter(
        Message.sender_id == user.id,
        Message.sent_at >= datetime.utcnow() - timedelta(minutes=1),
    ).count() >= CHAT_MESSAGES_PER_MINUTE:
        return {
            "ok": False,
            "error": "You are sending messages too quickly. Please wait a moment.",
        }, 429

    other_user = db.session.get(User, other_user_id)
    if other_user is None or not _conversation_allowed(user.id, other_user_id):
        return {"ok": False, "error": "You cannot message this user."}, 403

    message = Message(
        sender_id=user.id,
        receiver_id=other_user.id,
        text=text,
    )
    db.session.add(message)
    db.session.add(
        Notification(
            user_id=other_user.id,
            text=f"{user.first_name} sent you a message.",
            category="message",
            link_url=url_for("user.realtime_chat", other_user_id=user.id),
        )
    )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not save chat message")
        return {
            "ok": False,
            "error": "The message could not be sent. Please try again.",
        }, 500

    payload = {
        "id": message.id,
        "sender_id": user.id,
        "sender_name": user.username,
        "text": message.text,
        "sent_at": message.sent_at.isoformat(),
    }
    try:
        broadcast_message(user.id, other_user.id, text, payload=payload)
    except RealtimeDeliveryError:
        return {"ok": True, "realtime": False}, 202
    return {"ok": True, "realtime": True}, 200


@chat_bp.post("/typing")
@limiter.limit("30 per minute")
def chat_typing():
    data = request.get_json(silent=True)
    conversation, error = _request_other_user(data)
    if error:
        return error
    user, other_user = conversation
    try:
        broadcast_event(
            user.id,
            other_user.id,
            "typing",
            {"user_id": user.id, "is_typing": bool(data.get("is_typing"))},
        )
    except RealtimeDeliveryError:
        return {"ok": False, "error": "Real-time chat is temporarily unavailable."}, 503
    return {"ok": True}, 200


@chat_bp.post("/read")
def mark_messages_read():
    data = request.get_json(silent=True)
    conversation, error = _request_other_user(data)
    if error:
        return error
    user, other_user = conversation
    Message.query.filter_by(
        sender_id=other_user.id,
        receiver_id=user.id,
        is_read=False,
    ).update({Message.is_read: True})
    Notification.query.filter_by(
        user_id=user.id,
        category="message",
        link_url=url_for("user.realtime_chat", other_user_id=other_user.id),
        is_read=False,
    ).update({Notification.is_read: True})
    db.session.commit()
    return {"ok": True}, 200
