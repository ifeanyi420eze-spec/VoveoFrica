import re

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from flask_socketio import emit, join_room, leave_room
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from pkg import db, socketio
from pkg.models import Like, Match, Message, Notification, Report, User


user_routes = Blueprint("user", __name__)


def get_current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return db.session.get(User, user_id)


def require_user():
    user = get_current_user()
    if user is None:
        return None
    return user


def conversation_room(first_user_id, second_user_id):
    lower_id, higher_id = sorted((first_user_id, second_user_id))
    return f"conversation_{lower_id}_{higher_id}"


def users_are_matched(first_user_id, second_user_id):
    lower_id, higher_id = sorted((first_user_id, second_user_id))
    return Match.query.filter_by(
        first_user_id=lower_id,
        second_user_id=higher_id,
    ).first() is not None


@user_routes.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("voveo_pages/register.html")

    fields = {
        "first_name": request.form.get("first_name", "").strip(),
        "last_name": request.form.get("last_name", "").strip(),
        "username": request.form.get("username", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "phone_number": request.form.get("phone_number", "").strip(),
        "country": request.form.get("country", "").strip(),
        "city": request.form.get("city", "").strip(),
        "town": request.form.get("town", "").strip(),
    }
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not all(fields.values()) or not password or not confirm_password:
        return "Please fill in all the required fields.", 400
    if password != confirm_password:
        return "Passwords do not match. Please try again.", 400
    if len(password) < 8:
        return "Password must be at least 8 characters long.", 400
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter.", 400
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter.", 400
    if not re.search(r"[0-9]", password):
        return "Password must contain at least one digit.", 400
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return "Password must contain at least one special character.", 400
    if User.query.filter(
        or_(User.username == fields["username"], User.email == fields["email"])
    ).first():
        return "That username or email is already registered.", 409

    user = User(
        **fields,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()
    session.clear()
    session["user_id"] = user.id
    return redirect(url_for("user.profile"))


@user_routes.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember")=="1"
        if not identity or not password:
            return render_template(
                "voveo_pages/login.html",
                error="Username/email and password are required.",
            ), 400

        user = User.query.filter(
            or_(User.username == identity, User.email == identity.lower())
        ).first()

        if user is None or not check_password_hash(user.password_hash, password):
            return ("Invalid username, email, or password. Please try again."), 401

        session.clear()
        session["user_id"] = user.id
        session.permanent = remember
        return redirect(url_for("user.profile"))
    return render_template("voveo_pages/login.html")


@user_routes.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("user.login"))


@user_routes.route("/profile", methods=["GET", "POST"])
def profile():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        bio = request.form.get("bio", "").strip()
        if not username or not email:
            return "Please provide username and email to update your profile.", 400

        duplicate = User.query.filter(
            User.id != user.id,
            or_(User.username == username, User.email == email),
        ).first()
        if duplicate:
            return "That username or email is already in use.", 409

        user.username = username
        user.email = email
        user.bio = bio
        db.session.commit()
        return redirect(url_for("user.profile"))

    return render_template("user/pages/profile.html", user=user)


@user_routes.route("/dashboard")
def dashboard():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    matches = Match.query.filter(
        or_(Match.first_user_id == user.id, Match.second_user_id == user.id)
    ).all()
    messages = Message.query.filter(
        or_(Message.sender_id == user.id, Message.receiver_id == user.id)
    ).all()
    conversation_user_ids = {
        message.receiver_id if message.sender_id == user.id else message.sender_id
        for message in messages
    }
    profile_fields = (
        user.first_name,
        user.last_name,
        user.username,
        user.email,
        user.phone_number,
        user.country,
        user.city,
        user.town,
        user.bio,
    )
    profile_completion = round(
        sum(bool(value and value.strip()) for value in profile_fields)
        / len(profile_fields)
        * 100
    )
    return render_template(
        "user/pages/user_dashboard.html",
        user=user,
        match_count=len(matches),
        conversation_count=len(conversation_user_ids),
        profile_completion=profile_completion,
    )


@user_routes.route("/discover")
def discover():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))

    users = User.query.filter(User.id != user.id)
    existing_matches = Match.query.filter(
        or_(Match.first_user_id == user.id, Match.second_user_id == user.id)
    ).all()
    excluded_user_ids = {
        match.second_user_id if match.first_user_id == user.id else match.first_user_id
        for match in existing_matches
    }
    excluded_user_ids.update(
        liked_id
        for (liked_id,) in Like.query.with_entities(Like.liked_id).filter_by(
            liker_id=user.id
        )
    )
    if excluded_user_ids:
        users = users.filter(~User.id.in_(excluded_user_ids))

    country = request.args.get("country", "").strip()
    city = request.args.get("city", "").strip()
    if country:
        users = users.filter(User.country.ilike(f"%{country}%"))
    if city:
        users = users.filter(User.city.ilike(f"%{city}%"))
    return render_template("user/pages/discover.html", users=users.order_by(User.created_at.desc()).all())


@user_routes.route("/filter")
def filter_users():
    if require_user() is None:
        return redirect(url_for("user.login"))
    return redirect(url_for("user.discover", **request.args))


@user_routes.route("/likes")
def likes():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    likes_received = Like.query.filter_by(liked_id=user.id).order_by(
        Like.created_at.desc()
    ).all()
    likes_sent = Like.query.filter_by(liker_id=user.id).order_by(
        Like.created_at.desc()
    ).all()
    return render_template(
        "user/pages/likes.html", likes_received=likes_received, likes_sent=likes_sent
    )


@user_routes.route("/likes/<int:liked_id>", methods=["POST"])
def like_user(liked_id):
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    if liked_id == user.id:
        abort(400, "You cannot like your own profile.")

    liked_user = db.session.get(User, liked_id)
    if liked_user is None:
        abort(404)

    existing_like = Like.query.filter_by(liker_id=user.id, liked_id=liked_id).first()
    if existing_like is None:
        db.session.add(Like(liker_id=user.id, liked_id=liked_id))
        reverse_like = Like.query.filter_by(liker_id=liked_id, liked_id=user.id).first()
        if reverse_like:
            first_id, second_id = sorted((user.id, liked_id))
            existing_match = Match.query.filter_by(
                first_user_id=first_id, second_user_id=second_id
            ).first()
            if existing_match is None:
                db.session.add(Match(first_user_id=first_id, second_user_id=second_id))
        db.session.commit()

    return redirect(url_for("user.likes"))


@user_routes.route("/matches")
def matches():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    user_matches = Match.query.filter(
        or_(Match.first_user_id == user.id, Match.second_user_id == user.id)
    ).order_by(Match.created_at.desc()).all()
    return render_template(
        "user/pages/matches.html",
        matches=user_matches,
        current_user=user,
    )


@user_routes.route("/chats")
def chats():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))

    # Build one recent-message preview per matched conversation for the inbox.
    latest_messages = {}
    conversations = Message.query.filter(
        or_(Message.sender_id == user.id, Message.receiver_id == user.id)
    ).order_by(Message.sent_at.desc()).all()
    for message in conversations:
        other_user_id = (
            message.receiver_id if message.sender_id == user.id else message.sender_id
        )
        latest_messages.setdefault(other_user_id, message)

    user_matches = Match.query.filter(
        or_(Match.first_user_id == user.id, Match.second_user_id == user.id)
    ).order_by(Match.created_at.desc()).all()
    chat_list = []
    for match in user_matches:
        other_user_id = (
            match.second_user_id if match.first_user_id == user.id else match.first_user_id
        )
        other_user = db.session.get(User, other_user_id)
        if other_user is not None:
            chat_list.append((other_user, latest_messages.get(other_user_id)))

    return render_template("user/pages/chats.html", chat_list=chat_list)


@user_routes.route("/chats/<int:other_user_id>")
def realtime_chat(other_user_id):
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    other_user = db.session.get(User, other_user_id)
    if other_user is None:
        abort(404)
    if other_user.id == user.id or not users_are_matched(user.id, other_user.id):
        abort(403)

    conversation = Message.query.filter(
        or_(
            (Message.sender_id == user.id)
            & (Message.receiver_id == other_user.id),
            (Message.sender_id == other_user.id)
            & (Message.receiver_id == user.id),
        )
    ).order_by(Message.sent_at.asc()).all()
    has_unread_messages = False
    for message in conversation:
        if message.receiver_id == user.id:
            message.is_read = True
            has_unread_messages = True
    if has_unread_messages:
        db.session.commit()
    return render_template(
        "user/pages/realtime_chat.html",
        messages=conversation,
        other_user=other_user,
        current_user=user,
    )


@user_routes.route("/chat-box/<int:other_user_id>")
@user_routes.route("/chat_box/<int:other_user_id>")
def chat_box(other_user_id):
    """Keep legacy chat-box URLs working by opening the realtime conversation."""
    return redirect(url_for("user.realtime_chat", other_user_id=other_user_id))


@socketio.on("join_conversation", namespace="/chat")
def join_conversation(data):
    user = get_current_user()
    if user is None:
        return {"ok": False, "error": "You must be logged in to chat."}
    if not isinstance(data, dict):
        return {"ok": False, "error": "Invalid conversation."}

    try:
        other_user_id = int(data.get("other_user_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid conversation."}

    other_user = db.session.get(User, other_user_id)
    if (
        other_user is None
        or other_user.id == user.id
        or not users_are_matched(user.id, other_user.id)
    ):
        return {"ok": False, "error": "You cannot join this conversation."}

    join_room(conversation_room(user.id, other_user.id))
    return {"ok": True}


@socketio.on("leave_conversation", namespace="/chat")
def leave_conversation(data):
    user = get_current_user()
    if user is None or not isinstance(data, dict):
        return {"ok": False, "error": "Invalid conversation."}

    try:
        other_user_id = int(data.get("other_user_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid conversation."}

    other_user = db.session.get(User, other_user_id)
    if (
        other_user is None
        or other_user.id == user.id
        or not users_are_matched(user.id, other_user.id)
    ):
        return {"ok": False, "error": "You cannot leave this conversation."}

    leave_room(conversation_room(user.id, other_user.id))
    return {"ok": True}


@socketio.on("send_message", namespace="/chat")
def send_chat_message(data):
    user = get_current_user()
    if user is None:
        return {"ok": False, "error": "You must be logged in to send messages."}
    if not isinstance(data, dict):
        return {"ok": False, "error": "Invalid message."}

    try:
        other_user_id = int(data.get("other_user_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid conversation."}

    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "error": "Please enter a message."}
    text = text.strip()
    if len(text) > 5000:
        return {"ok": False, "error": "Messages cannot be longer than 5000 characters."}

    other_user = db.session.get(User, other_user_id)
    if (
        other_user is None
        or other_user.id == user.id
        or not users_are_matched(user.id, other_user.id)
    ):
        return {"ok": False, "error": "You cannot message this user."}

    message = Message(
        sender_id=user.id,
        receiver_id=other_user.id,
        text=text,
    )
    try:
        db.session.add(message)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not save chat message")
        return {"ok": False, "error": "The message could not be sent. Please try again."}

    emit(
        "new_message",
        {
            "id": message.id,
            "sender_id": user.id,
            "sender_name": user.username,
            "text": message.text,
            "sent_at": message.sent_at.isoformat(),
        },
        to=conversation_room(user.id, other_user.id),
    )
    return {"ok": True}


@user_routes.route("/notifications")
def notifications():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    user_notifications = Notification.query.filter_by(user_id=user.id).order_by(
        Notification.created_at.desc()
    ).all()
    return render_template(
        "user/pages/user_dashboard.html",
        user=user,
        notifications=user_notifications,
    )


@user_routes.route("/settings", methods=["GET", "POST"])
def settings():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    if request.method == "POST":
        user.bio = request.form.get("bio", "").strip()
        db.session.commit()
        return redirect(url_for("user.settings"))
    return render_template("user/pages/settings.html", user=user)


@user_routes.route("/report/<int:reported_user_id>", methods=["GET", "POST"])
def report_user(reported_user_id):
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    reported_user = db.session.get(User, reported_user_id)
    if reported_user is None:
        abort(404)
    if reported_user.id == user.id:
        abort(400, "You cannot report your own profile.")

    if request.method == "POST":
        reason = request.form.get("reason", "").strip()
        details = request.form.get("details", "").strip()
        if not reason:
            return "Please provide a reason for the report.", 400
        db.session.add(
            Report(
                reporter_id=user.id,
                reported_user_id=reported_user.id,
                reason=reason,
                details=details,
            )
        )
        db.session.commit()
        return redirect(url_for("user.discover"))

    return render_template("user/pages/report.html", reported_user=reported_user)
