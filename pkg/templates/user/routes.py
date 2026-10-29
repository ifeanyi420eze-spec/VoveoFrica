import hashlib
import hmac
import json
import re
import secrets
from io import BytesIO
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from flask_socketio import emit, join_room, leave_room
from sqlalchemy import case, func, or_
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from pkg import csrf, db, limiter, socketio
from pkg.content_moderation import contains_profanity
from pkg.email_auth import (
    EmailAuthConfigurationError,
    EmailAuthDeliveryError,
    send_email_code,
)
from pkg.payments import paystack_configuration_is_ready
from pkg.models import (
    Block,
    DailyLikeUsage,
    EmailAuthChallenge,
    Like,
    Match,
    Message,
    Notification,
    Report,
    Subscription,
    SubscriptionPlan,
    User,
)


user_routes = Blueprint("user", __name__)

PROFILE_PROMPTS = (
    "A perfect weekend looks like...",
    "The little things that make me happy...",
    "The best way to get to know me is...",
    "I am looking for someone who...",
)
RELATIONSHIP_GOALS = ("Long-term", "Marriage", "Casual dating", "Friendship")
REPORT_REASONS = (
    "Harassment",
    "Fake profile",
    "Inappropriate content",
    "Spam",
    "Other",
)
FREE_DAILY_LIKE_LIMIT = 10
PREMIUM_DAILY_LIKE_LIMIT = 50
PAYSTACK_API_BASE = "https://api.paystack.co"
EMAIL_AUTH_CODE_LIFETIME = timedelta(minutes=10)
EMAIL_AUTH_RESEND_DELAY = timedelta(seconds=60)
EMAIL_AUTH_MAX_ATTEMPTS = 5
CHAT_MESSAGES_PER_MINUTE = 30


class EmailAuthRateLimit(Exception):
    pass


def _mask_email(email):
    local, separator, domain = email.partition("@")
    if not separator:
        return email
    return f"{local[:1]}{'*' * max(1, len(local) - 1)}@{domain}"


def _start_email_auth_challenge(user, purpose):
    now = datetime.utcnow()
    latest = (
        EmailAuthChallenge.query.filter_by(
            user_id=user.id,
            purpose=purpose,
        )
        .order_by(EmailAuthChallenge.created_at.desc())
        .first()
    )
    existing = (
        EmailAuthChallenge.query.filter_by(user_id=user.id, purpose=purpose)
        .filter(
            EmailAuthChallenge.consumed_at.is_(None),
            EmailAuthChallenge.expires_at > now,
            EmailAuthChallenge.attempts < EMAIL_AUTH_MAX_ATTEMPTS,
        )
        .order_by(EmailAuthChallenge.created_at.desc())
        .first()
    )
    if latest and latest.created_at > now - EMAIL_AUTH_RESEND_DELAY:
        if existing and existing.id == latest.id:
            session["email_auth_challenge_id"] = existing.id
            return existing, False
        raise EmailAuthRateLimit("Please wait before requesting another code.")

    EmailAuthChallenge.query.filter_by(
        user_id=user.id,
        purpose=purpose,
    ).filter(EmailAuthChallenge.consumed_at.is_(None)).update(
        {"consumed_at": now},
        synchronize_session=False,
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = EmailAuthChallenge(
        user_id=user.id,
        purpose=purpose,
        code_digest="",
        attempts=0,
        created_at=now,
        expires_at=now + EMAIL_AUTH_CODE_LIFETIME,
    )
    db.session.add(challenge)
    db.session.flush()
    challenge.code_digest = hmac.new(
        current_app.secret_key.encode(),
        f"{challenge.id}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()
    db.session.commit()

    session["email_auth_challenge_id"] = challenge.id
    send_email_code(user.email, code, purpose)
    return challenge, True


def _email_auth_page(error=None):
    challenge_id = session.get("email_auth_challenge_id")
    challenge = db.session.get(EmailAuthChallenge, challenge_id)
    if challenge is None or (
        challenge.consumed_at is not None
        and challenge.attempts < EMAIL_AUTH_MAX_ATTEMPTS
    ):
        session.pop("email_auth_challenge_id", None)
        return redirect(url_for("user.login"))
    user = db.session.get(User, challenge.user_id)
    if user is None:
        session.pop("email_auth_challenge_id", None)
        return redirect(url_for("user.login"))
    return render_template(
        "voveo_pages/email_verification.html",
        error=error,
        purpose=challenge.purpose,
        masked_email=_mask_email(user.email),
        expired=(
            challenge.expires_at <= datetime.utcnow()
            or challenge.attempts >= EMAIL_AUTH_MAX_ATTEMPTS
        ),
        resend_wait=(
            max(0, int((challenge.created_at + EMAIL_AUTH_RESEND_DELAY - datetime.utcnow()).total_seconds()))
            if challenge.expires_at > datetime.utcnow()
            else 0
        ),
    )


def has_active_premium(user):
    now = datetime.utcnow()
    return (
        Subscription.query.filter(
            Subscription.user_id == user.id,
            Subscription.plan_type == "premium",
            Subscription.status == "active",
            Subscription.starts_at <= now,
            Subscription.ends_at > now,
        ).first()
        is not None
    )


def active_subscription(user, plan_type):
    now = datetime.utcnow()
    return (
        Subscription.query.filter(
            Subscription.user_id == user.id,
            Subscription.plan_type == plan_type,
            Subscription.status == "active",
            Subscription.starts_at <= now,
            Subscription.ends_at > now,
        )
        .order_by(Subscription.ends_at.desc())
        .first()
    )


def daily_like_limit(user):
    return PREMIUM_DAILY_LIKE_LIMIT if has_active_premium(user) else FREE_DAILY_LIKE_LIMIT


def daily_likes_used(user):
    today = datetime.utcnow().date()
    recorded_usage = DailyLikeUsage.query.filter_by(
        user_id=user.id,
        usage_date=today,
    ).first()
    day_start = datetime.combine(today, datetime.min.time())
    likes_count = Like.query.filter(
        Like.liker_id == user.id,
        Like.created_at >= day_start,
    ).count()
    return max(recorded_usage.likes_used if recorded_usage else 0, likes_count)


def paystack_request(path, payload=None):
    secret_key = current_app.config.get("PAYSTACK_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("Paystack checkout is not configured.")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    provider_request = Request(
        f"{PAYSTACK_API_BASE}{path}",
        data=body,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST" if body is not None else "GET",
    )
    try:
        with urlopen(provider_request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        current_app.logger.exception("Paystack request failed")
        raise RuntimeError("Payment service is temporarily unavailable.") from error
    if not isinstance(result, dict) or result.get("status") is not True:
        current_app.logger.error("Paystack returned an unsuccessful API response.")
        raise RuntimeError("Payment service could not process this request.")
    return result.get("data")


def activate_verified_payment(payment_reference):
    subscription = Subscription.query.filter_by(
        payment_reference=payment_reference,
        payment_provider="paystack",
    ).first()
    if subscription is None:
        return "missing"
    if subscription.status == "active":
        return "active"
    if subscription.status != "pending":
        return subscription.status

    transaction = paystack_request(
        f"/transaction/verify/{payment_reference}"
    )
    if not isinstance(transaction, dict):
        return "invalid"
    expected_amount = int(
        (Decimal(subscription.amount_ngn) * 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    customer = transaction.get("customer")
    if transaction.get("status") in {"failed", "abandoned", "reversed"}:
        subscription.status = "failed"
        db.session.commit()
        return "failed"
    if transaction.get("status") != "success":
        return "pending"
    if (
        transaction.get("reference") != payment_reference
        or transaction.get("amount") != expected_amount
        or transaction.get("currency") != "NGN"
        or not isinstance(customer, dict)
        or (customer.get("email") or "").strip().lower()
        != (subscription.payment_email or "").strip().lower()
    ):
        subscription.status = "failed"
        db.session.commit()
        return "invalid"

    if db.session.get(User, subscription.user_id, with_for_update=True) is None:
        return "missing"
    subscription = Subscription.query.filter_by(
        payment_reference=payment_reference,
        payment_provider="paystack",
    ).with_for_update().first()
    if subscription is None:
        return "missing"
    if subscription.status == "active":
        return "active"
    if subscription.status != "pending":
        return subscription.status

    now = datetime.utcnow()
    active_passes = (
        Subscription.query.filter(
            Subscription.user_id == subscription.user_id,
            Subscription.plan_type == subscription.plan_type,
            Subscription.status == "active",
            Subscription.ends_at > now,
        )
        .with_for_update()
        .all()
    )
    current_expiry = max(
        (
            active_pass.ends_at
            for active_pass in active_passes
            if active_pass.ends_at is not None
        ),
        default=None,
    )
    starts_at = max(now, current_expiry) if current_expiry else now
    subscription.status = "active"
    subscription.paid_at = now
    subscription.starts_at = starts_at
    subscription.ends_at = starts_at + timedelta(days=subscription.duration_days)
    db.session.add(
        Notification(
            user_id=subscription.user_id,
            text=(
                "Your one-time Premium pass is active."
                if subscription.plan_type == "premium"
                else "Your 24-hour profile Boost is active."
            ),
            category="subscription",
            link_url=url_for("user.subscription_account"),
        )
    )
    db.session.commit()
    return "active"


@user_routes.app_context_processor
def inject_unread_notification_count():
    user_id = session.get("user_id")
    if user_id is None:
        return {"unread_notification_count": 0}
    return {
        "unread_notification_count": Notification.query.filter_by(
            user_id=user_id,
            is_read=False,
        ).count()
    }


def create_notification(user_id, text, category, link_url):
    db.session.add(
        Notification(
            user_id=user_id,
            text=text,
            category=category,
            link_url=link_url,
        )
    )


def save_profile_photo(uploaded_file):
    header = uploaded_file.stream.read(12)
    if header.startswith(b"\xff\xd8\xff"):
        extension = "jpg"
    elif header.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = "png"
    elif header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        extension = "webp"
    else:
        raise ValueError("Choose a valid JPG, PNG, or WebP image.")

    uploaded_file.stream.seek(0)
    filename = f"{secrets.token_hex(16)}.{extension}"
    bucket = current_app.config.get("PROFILE_PHOTO_S3_BUCKET")
    if bucket:
        import boto3

        key = f"profile-photos/{filename}"
        client = boto3.client("s3", region_name=current_app.config.get("AWS_REGION"))
        client.upload_fileobj(
            uploaded_file.stream,
            bucket,
            key,
            ExtraArgs={
                "ContentType": {
                    "jpg": "image/jpeg",
                    "png": "image/png",
                    "webp": "image/webp",
                }[extension],
                "CacheControl": "private, max-age=3600",
            },
        )
        return f"s3:{key}"

    upload_directory = Path(current_app.instance_path) / "profile_photos"
    upload_directory.mkdir(parents=True, exist_ok=True)
    uploaded_file.save(upload_directory / filename)
    return filename


def delete_profile_photo(filename):
    if not filename:
        return
    bucket = current_app.config.get("PROFILE_PHOTO_S3_BUCKET")
    if filename.startswith("s3:"):
        key = filename[3:]
        if not bucket or not re.fullmatch(
            r"profile-photos/[a-f0-9]{32}\.(?:jpg|png|webp)", key
        ):
            return
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        client = boto3.client("s3", region_name=current_app.config.get("AWS_REGION"))
        try:
            client.delete_object(Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError):
            current_app.logger.exception("Could not delete profile photo from S3")
        return
    if not re.fullmatch(r"[a-f0-9]{32}\.(?:jpg|png|webp)", filename):
        return
    photo_path = Path(current_app.instance_path) / "profile_photos" / filename
    photo_path.unlink(missing_ok=True)


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


def users_are_blocked(first_user_id, second_user_id):
    return Block.query.filter(
        or_(
            (Block.blocker_id == first_user_id) & (Block.blocked_id == second_user_id),
            (Block.blocker_id == second_user_id) & (Block.blocked_id == first_user_id),
        )
    ).first() is not None


def get_discoverable_users(user):
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
        ).all()
    )
    excluded_user_ids.update(
        block.blocked_id if block.blocker_id == user.id else block.blocker_id
        for block in Block.query.filter(
            or_(Block.blocker_id == user.id, Block.blocked_id == user.id)
        )
    )
    if excluded_user_ids:
        users = users.filter(~User.id.in_(excluded_user_ids))

    premium = has_active_premium(user)
    country = request.args.get(
        "country", user.preferred_country if premium else ""
    ).strip()
    city = request.args.get("city", user.preferred_city if premium else "").strip()
    goal = request.args.get("goal", "").strip()
    selected_goals = (
        ([goal] if goal else [])
        if "goal" in request.args
        else [
            item.strip()
            for item in (user.preferred_goals if premium else "").split(",")
            if item.strip()
        ]
    )
    selected_interests = [
        item.strip()
        for item in request.args.get(
            "interests", user.preferred_interests if premium else ""
        ).split(",")
        if item.strip()
    ]
    if country:
        users = users.filter(User.country.ilike(f"%{country}%"))
    if city:
        users = users.filter(User.city.ilike(f"%{city}%"))
    if selected_goals:
        users = users.filter(User.relationship_goal.in_(selected_goals))
    for interest in selected_interests:
        users = users.filter(User.interests.ilike(f"%{interest}%"))
    boosted_users = db.session.query(Subscription.user_id).filter(
        Subscription.plan_type == "boost",
        Subscription.status == "active",
        Subscription.starts_at <= datetime.utcnow(),
        Subscription.ends_at > datetime.utcnow(),
    ).distinct()
    return users.order_by(
        case((User.id.in_(boosted_users), 0), else_=1),
        User.created_at.desc(),
    ).limit(100).all()


@user_routes.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
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
    relationship_goal = request.form.get("relationship_goal", "").strip()
    interests = request.form.get("interests", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not all(fields.values()) or not password or not confirm_password:
        return "Please fill in all the required fields.", 400
    if relationship_goal and relationship_goal not in RELATIONSHIP_GOALS:
        return "Choose one of the available relationship goals.", 400
    if len(interests) > 500:
        return "Interests must be 500 characters or fewer.", 400
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
        email_verified=False,
        relationship_goal=relationship_goal,
        interests=interests,
    )
    db.session.add(user)
    db.session.commit()
    session.clear()
    try:
        _start_email_auth_challenge(user, "registration")
    except EmailAuthRateLimit as error:
        return _email_auth_page(str(error)), 429
    except (EmailAuthConfigurationError, EmailAuthDeliveryError) as error:
        return _email_auth_page(str(error)), 503
    return redirect(url_for("user.verify_email"))


@user_routes.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
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
        purpose = "login" if user.email_verified else "registration"
        session["remember_login"] = remember
        try:
            _start_email_auth_challenge(user, purpose)
        except EmailAuthRateLimit as error:
            return render_template("voveo_pages/login.html", error=str(error)), 429
        except (EmailAuthConfigurationError, EmailAuthDeliveryError) as error:
            return _email_auth_page(str(error)), 503
        return redirect(url_for("user.verify_email"))
    return render_template("voveo_pages/login.html")


@user_routes.route("/verify-email", methods=["GET", "POST"])
@limiter.limit("10 per 10 minutes", methods=["POST"])
def verify_email():
    if request.method == "GET":
        return _email_auth_page()

    challenge_id = session.get("email_auth_challenge_id")
    challenge = (
        EmailAuthChallenge.query.filter_by(id=challenge_id)
        .with_for_update()
        .first()
    )
    now = datetime.utcnow()
    if challenge is None or challenge.consumed_at is not None:
        session.pop("email_auth_challenge_id", None)
        return redirect(url_for("user.login"))

    if challenge.expires_at <= now:
        return _email_auth_page("That code has expired. Request a new one.")
    if challenge.attempts >= EMAIL_AUTH_MAX_ATTEMPTS:
        challenge.consumed_at = now
        db.session.commit()
        return _email_auth_page("Too many incorrect attempts. Request a new code.")

    submitted_code = request.form.get("code", "").strip()
    expected_digest = hmac.new(
        current_app.secret_key.encode(),
        f"{challenge.id}:{submitted_code}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if (
        len(submitted_code) != 6
        or not submitted_code.isdigit()
        or not hmac.compare_digest(challenge.code_digest, expected_digest)
    ):
        challenge.attempts += 1
        if challenge.attempts >= EMAIL_AUTH_MAX_ATTEMPTS:
            challenge.consumed_at = now
        db.session.commit()
        message = (
            "Too many incorrect attempts. Request a new code."
            if challenge.attempts >= EMAIL_AUTH_MAX_ATTEMPTS
            else "That code is not correct. Please try again."
        )
        return _email_auth_page(message), 400

    user = db.session.get(User, challenge.user_id)
    if user is None:
        db.session.rollback()
        session.clear()
        return redirect(url_for("user.login"))

    challenge.consumed_at = now
    if challenge.purpose == "registration":
        user.email_verified = True
    db.session.commit()

    remember = bool(session.get("remember_login")) if challenge.purpose == "login" else False
    session.clear()
    session["user_id"] = user.id
    session["is_admin"] = user.email.strip().lower() in current_app.config["ADMIN_EMAILS"]
    session.permanent = remember
    return redirect(url_for("user.profile"))


@user_routes.route("/verify-email/resend", methods=["POST"])
@limiter.limit("3 per 10 minutes")
def resend_email_code():
    challenge_id = session.get("email_auth_challenge_id")
    current_challenge = db.session.get(EmailAuthChallenge, challenge_id)
    if current_challenge is None or (
        current_challenge.consumed_at is not None
        and current_challenge.attempts < EMAIL_AUTH_MAX_ATTEMPTS
    ):
        session.pop("email_auth_challenge_id", None)
        return redirect(url_for("user.login"))

    user = db.session.get(User, current_challenge.user_id)
    if user is None:
        session.clear()
        return redirect(url_for("user.login"))

    try:
        challenge, sent = _start_email_auth_challenge(user, current_challenge.purpose)
    except (EmailAuthConfigurationError, EmailAuthDeliveryError) as error:
        return _email_auth_page(str(error)), 503

    message = (
        "A new code has been sent to your email."
        if sent
        else "Please wait before requesting another code."
    )
    return _email_auth_page(message)


@user_routes.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("user.login"))


@user_routes.route("/profile", methods=["GET", "POST"])
def profile():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))

    def profile_error(message, status):
        return (
            render_template(
                "user/pages/profile.html",
                user=user,
                profile_prompts=PROFILE_PROMPTS,
                relationship_goals=RELATIONSHIP_GOALS,
                is_premium=has_active_premium(user),
                error=message,
            ),
            status,
        )

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        bio = request.form.get("bio", "").strip()
        interests = request.form.get("interests", "").strip()
        profile_prompt = request.form.get("profile_prompt", "").strip()
        profile_answer = request.form.get("profile_answer", "").strip()
        relationship_goal = request.form.get("relationship_goal", "").strip()
        photo = request.files.get("profile_photo")
        remove_photo = request.form.get("remove_photo") == "1"
        if not username or not email:
            return profile_error("Please provide a username and email.", 400)
        if len(interests) > 500:
            return profile_error("Interests must be 500 characters or fewer.", 400)
        if profile_prompt and profile_prompt not in PROFILE_PROMPTS:
            return profile_error("Choose one of the available profile prompts.", 400)
        if len(profile_answer) > 280:
            return profile_error("Your prompt answer must be 280 characters or fewer.", 400)
        if relationship_goal and relationship_goal not in RELATIONSHIP_GOALS:
            return profile_error("Choose one of the available relationship goals.", 400)
        if profile_answer and not profile_prompt:
            return profile_error("Choose a prompt for your profile answer.", 400)

        duplicate = User.query.filter(
            User.id != user.id,
            or_(User.username == username, User.email == email),
        ).first()
        if duplicate:
            return profile_error("That username or email is already in use.", 409)

        new_photo = None
        if photo and photo.filename:
            try:
                new_photo = save_profile_photo(photo)
            except ValueError as error:
                return profile_error(str(error), 400)

        old_photo = user.profile_photo
        user.username = username
        user.email = email
        user.bio = bio
        user.interests = interests
        user.profile_prompt = profile_prompt
        user.profile_answer = profile_answer
        user.relationship_goal = relationship_goal
        if new_photo:
            user.profile_photo = new_photo
        elif remove_photo:
            user.profile_photo = None
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            if new_photo:
                delete_profile_photo(new_photo)
            current_app.logger.exception("Could not save profile changes")
            raise

        if (new_photo or remove_photo) and old_photo:
            delete_profile_photo(old_photo)
        return redirect(url_for("user.profile"))

    return render_template(
        "user/pages/profile.html",
        user=user,
        profile_prompts=PROFILE_PROMPTS,
        relationship_goals=RELATIONSHIP_GOALS,
        is_premium=has_active_premium(user),
    )


@user_routes.route("/profile-photos/<path:filename>")
def profile_photo(filename):
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    photo_key = (
        filename[3:]
        if filename.startswith("s3:")
        else f"profile-photos/{filename}"
    )
    if not re.fullmatch(
        r"profile-photos/[a-f0-9]{32}\.(?:jpg|png|webp)", photo_key
    ):
        abort(404)
    photo_owner = User.query.filter_by(profile_photo=filename).first()
    if photo_owner is None or (
        photo_owner.id != user.id and users_are_blocked(user.id, photo_owner.id)
    ):
        abort(404)
    if filename.startswith("s3:"):
        bucket = current_app.config.get("PROFILE_PHOTO_S3_BUCKET")
        if not bucket:
            abort(404)
        import boto3

        client = boto3.client("s3", region_name=current_app.config.get("AWS_REGION"))
        image = client.get_object(Bucket=bucket, Key=photo_key)
        image_body = image["Body"]
        try:
            image_data = image_body.read()
        finally:
            image_body.close()
        response = send_file(
            BytesIO(image_data),
            mimetype=image.get("ContentType", "application/octet-stream"),
            max_age=3600,
            conditional=True,
        )
        response.headers["Cache-Control"] = "private, max-age=3600"
        return response
    return send_from_directory(
        Path(current_app.instance_path) / "profile_photos",
        photo_key.rsplit("/", 1)[-1],
        max_age=3600,
    )


@user_routes.route("/dashboard")
def dashboard():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    matches_query = Match.query.filter(
        or_(Match.first_user_id == user.id, Match.second_user_id == user.id)
    )
    match_count = matches_query.count()
    conversation_count = (
        db.session.query(
            func.count(
                func.distinct(
                    case(
                        (Message.sender_id == user.id, Message.receiver_id),
                        else_=Message.sender_id,
                    )
                )
            )
        )
        .filter(or_(Message.sender_id == user.id, Message.receiver_id == user.id))
        .scalar()
        or 0
    )
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
        user.profile_photo,
        user.interests,
        user.relationship_goal,
        user.profile_answer,
    )
    profile_completion = round(
        sum(
            bool(value and (not isinstance(value, str) or value.strip()))
            for value in profile_fields
        )
        / len(profile_fields)
        * 100
    )
    return render_template(
        "user/pages/user_dashboard.html",
        user=user,
        match_count=match_count,
        conversation_count=conversation_count,
        profile_completion=profile_completion,
        premium_subscription=active_subscription(user, "premium"),
        active_boost=active_subscription(user, "boost"),
        is_premium=has_active_premium(user),
        daily_like_limit=daily_like_limit(user),
        daily_likes_used=daily_likes_used(user),
        recent_notifications=Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc())
        .limit(3)
        .all(),
    )


@user_routes.route("/discover")
def discover():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    return render_template(
        "user/pages/discover.html",
        users=get_discoverable_users(user),
        is_premium=has_active_premium(user),
        daily_like_limit=daily_like_limit(user),
        daily_likes_used=daily_likes_used(user),
    )


@user_routes.route("/explore")
def explore():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    return render_template(
        "user/pages/explore.html",
        users=get_discoverable_users(user),
        country=request.args.get(
            "country", user.preferred_country if has_active_premium(user) else ""
        ).strip(),
        city=request.args.get(
            "city", user.preferred_city if has_active_premium(user) else ""
        ).strip(),
        goal=request.args.get("goal", "").strip(),
        interests=request.args.get(
            "interests",
            user.preferred_interests if has_active_premium(user) else "",
        ).strip(),
        is_premium=has_active_premium(user),
        daily_like_limit=daily_like_limit(user),
        daily_likes_used=daily_likes_used(user),
    )


@user_routes.route("/connections")
def connections():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    user_matches = Match.query.filter(
        or_(Match.first_user_id == user.id, Match.second_user_id == user.id)
    ).order_by(Match.created_at.desc()).all()
    user_matches = [
        match
        for match in user_matches
        if not users_are_blocked(
            user.id,
            match.second_user_id
            if match.first_user_id == user.id
            else match.first_user_id,
        )
    ]
    return render_template(
        "user/pages/connections.html",
        matches=user_matches,
        current_user=user,
    )


@user_routes.route("/filter", methods=["GET", "POST"])
def filter_users():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    if request.method == "POST":
        if not has_active_premium(user):
            flash("Saved discovery preferences are a Premium feature. You can still search with filters in Explore.", "info")
            return redirect(url_for("root.subscription"))
        if request.form.get("reset") == "1":
            user.preferred_goals = ""
            user.preferred_interests = ""
            user.preferred_country = ""
            user.preferred_city = ""
            db.session.commit()
            return redirect(url_for("user.explore"))
        goals = [
            goal
            for goal in request.form.getlist("preferred_goals")
            if goal in RELATIONSHIP_GOALS
        ]
        user.preferred_goals = ",".join(dict.fromkeys(goals))
        user.preferred_interests = request.form.get("preferred_interests", "").strip()[:500]
        user.preferred_country = request.form.get("preferred_country", "").strip()[:80]
        user.preferred_city = request.form.get("preferred_city", "").strip()[:80]
        db.session.commit()
        return redirect(url_for("user.explore"))
    return render_template(
        "user/pages/filter.html",
        user=user,
        relationship_goals=RELATIONSHIP_GOALS,
        is_premium=has_active_premium(user),
    )


@user_routes.route("/likes")
def likes():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    premium = has_active_premium(user)
    blocked_user_ids = [
        block.blocked_id if block.blocker_id == user.id else block.blocker_id
        for block in Block.query.filter(
            or_(Block.blocker_id == user.id, Block.blocked_id == user.id)
        )
    ]
    received_likes_query = Like.query.filter_by(liked_id=user.id)
    if blocked_user_ids:
        received_likes_query = received_likes_query.filter(
            ~Like.liker_id.in_(blocked_user_ids)
        )
    likes_received_count = received_likes_query.count()
    likes_received = (
        received_likes_query.order_by(Like.created_at.desc()).all()
        if premium
        else []
    )
    likes_received = [
        like for like in likes_received
        if not users_are_blocked(user.id, like.liker_id)
    ]
    likes_sent = Like.query.filter_by(liker_id=user.id).order_by(
        Like.created_at.desc()
    ).all()
    return render_template(
        "user/pages/likes.html",
        likes_received=likes_received,
        likes_received_count=likes_received_count,
        likes_sent=likes_sent,
        is_premium=premium,
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
    if users_are_blocked(user.id, liked_id):
        abort(403)

    db.session.get(User, user.id, with_for_update=True)
    existing_like = Like.query.filter_by(liker_id=user.id, liked_id=liked_id).first()
    if existing_like is None:
        today = datetime.utcnow().date()
        usage = DailyLikeUsage.query.filter_by(
            user_id=user.id,
            usage_date=today,
        ).with_for_update().first()
        used_likes = daily_likes_used(user)
        like_limit = daily_like_limit(user)
        if used_likes >= like_limit:
            flash(
                f"You have used today's {like_limit} likes. Upgrade to Premium for up to {PREMIUM_DAILY_LIKE_LIMIT} likes a day.",
                "info",
            )
            return redirect(url_for("root.subscription"))
        if usage is None:
            usage = DailyLikeUsage(
                user_id=user.id,
                usage_date=today,
                likes_used=used_likes + 1,
            )
            db.session.add(usage)
        else:
            usage.likes_used = used_likes + 1
        db.session.add(Like(liker_id=user.id, liked_id=liked_id))
        create_notification(
            liked_id,
            "Someone liked your profile. Premium members can see who.",
            "like",
            url_for("user.likes"),
        )
        reverse_like = Like.query.filter_by(liker_id=liked_id, liked_id=user.id).first()
        if reverse_like:
            first_id, second_id = sorted((user.id, liked_id))
            existing_match = Match.query.filter_by(
                first_user_id=first_id, second_user_id=second_id
            ).first()
            if existing_match is None:
                db.session.add(Match(first_user_id=first_id, second_user_id=second_id))
                create_notification(
                    user.id,
                    f"You and {liked_user.first_name} matched!",
                    "match",
                    url_for("user.realtime_chat", other_user_id=liked_id),
                )
                create_notification(
                    liked_id,
                    f"You and {user.first_name} matched!",
                    "match",
                    url_for("user.realtime_chat", other_user_id=user.id),
                )
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
    user_matches = [
        match
        for match in user_matches
        if not users_are_blocked(
            user.id,
            match.second_user_id
            if match.first_user_id == user.id
            else match.first_user_id,
        )
    ]
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
        if other_user is not None and not users_are_blocked(user.id, other_user_id):
            unread_count = Message.query.filter_by(
                sender_id=other_user_id,
                receiver_id=user.id,
                is_read=False,
            ).count()
            chat_list.append(
                (other_user, latest_messages.get(other_user_id), unread_count)
            )

    return render_template("user/pages/chats.html", chat_list=chat_list)


@user_routes.route("/chats/<int:other_user_id>")
def realtime_chat(other_user_id):
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    other_user = db.session.get(User, other_user_id)
    if other_user is None:
        abort(404)
    if (
        other_user.id == user.id
        or not users_are_matched(user.id, other_user.id)
        or users_are_blocked(user.id, other_user.id)
    ):
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
        Notification.query.filter_by(
            user_id=user.id,
            category="message",
            link_url=url_for("user.realtime_chat", other_user_id=other_user.id),
            is_read=False,
        ).update({Notification.is_read: True})
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
        or users_are_blocked(user.id, other_user.id)
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
        or users_are_blocked(user.id, other_user.id)
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
    if contains_profanity(text):
        return {
            "ok": False,
            "error": "Please keep messages respectful. This message contains language that cannot be sent.",
        }
    recent_message_count = Message.query.filter(
        Message.sender_id == user.id,
        Message.sent_at >= datetime.utcnow() - timedelta(minutes=1),
    ).count()
    if recent_message_count >= CHAT_MESSAGES_PER_MINUTE:
        return {
            "ok": False,
            "error": "You are sending messages too quickly. Please wait a moment.",
        }

    other_user = db.session.get(User, other_user_id)
    if (
        other_user is None
        or other_user.id == user.id
        or not users_are_matched(user.id, other_user.id)
        or users_are_blocked(user.id, other_user.id)
    ):
        return {"ok": False, "error": "You cannot message this user."}

    message = Message(
        sender_id=user.id,
        receiver_id=other_user.id,
        text=text,
    )
    try:
        db.session.add(message)
        create_notification(
            other_user.id,
            f"{user.first_name} sent you a message.",
            "message",
            url_for("user.realtime_chat", other_user_id=user.id),
        )
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


@socketio.on("typing", namespace="/chat")
def chat_typing(data):
    user = get_current_user()
    if user is None or not isinstance(data, dict):
        return {"ok": False}
    try:
        other_user_id = int(data.get("other_user_id"))
    except (TypeError, ValueError):
        return {"ok": False}
    if (
        other_user_id == user.id
        or not users_are_matched(user.id, other_user_id)
        or users_are_blocked(user.id, other_user_id)
    ):
        return {"ok": False}
    emit(
        "typing",
        {"user_id": user.id, "is_typing": bool(data.get("is_typing"))},
        to=conversation_room(user.id, other_user_id),
        include_self=False,
    )
    return {"ok": True}


@socketio.on("mark_messages_read", namespace="/chat")
def mark_messages_read(data):
    user = get_current_user()
    if user is None or not isinstance(data, dict):
        return {"ok": False}
    try:
        other_user_id = int(data.get("other_user_id"))
    except (TypeError, ValueError):
        return {"ok": False}
    if (
        other_user_id == user.id
        or not users_are_matched(user.id, other_user_id)
        or users_are_blocked(user.id, other_user_id)
    ):
        return {"ok": False}
    Message.query.filter_by(
        sender_id=other_user_id,
        receiver_id=user.id,
        is_read=False,
    ).update({Message.is_read: True})
    Notification.query.filter_by(
        user_id=user.id,
        category="message",
        link_url=url_for("user.realtime_chat", other_user_id=other_user_id),
        is_read=False,
    ).update({Notification.is_read: True})
    db.session.commit()
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
        "user/pages/notifications.html", notifications=user_notifications
    )


@user_routes.route("/notifications/<int:notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id):
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    notification = Notification.query.filter_by(
        id=notification_id, user_id=user.id
    ).first_or_404()
    notification.is_read = True
    db.session.commit()
    target = notification.link_url
    parsed_target = urlsplit(target or "")
    if (
        target
        and parsed_target.path.startswith("/")
        and not parsed_target.netloc
        and not parsed_target.scheme
        and "\\" not in target
    ):
        return redirect(target)
    return redirect(url_for("user.notifications"))


@user_routes.route("/notifications/read-all", methods=["POST"])
def mark_all_notifications_read():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    Notification.query.filter_by(user_id=user.id, is_read=False).update(
        {Notification.is_read: True}
    )
    db.session.commit()
    return redirect(url_for("user.notifications"))


@user_routes.route("/verification", methods=["GET", "POST"])
def verification():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    if request.method == "POST":
        if user.verification_status == "verified":
            abort(409, "Your profile is already verified.")
        user.verification_status = "pending"
        user.verification_requested_at = datetime.utcnow()
        user.verification_reviewed_at = None
        db.session.commit()
        return redirect(url_for("user.verification"))
    return render_template("user/pages/verification.html", user=user)


@user_routes.route("/block/<int:blocked_user_id>", methods=["POST"])
def block_user(blocked_user_id):
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    if blocked_user_id == user.id:
        abort(400, "You cannot block your own profile.")
    blocked_user = db.session.get(User, blocked_user_id)
    if blocked_user is None:
        abort(404)
    if not Block.query.filter_by(
        blocker_id=user.id, blocked_id=blocked_user_id
    ).first():
        db.session.add(Block(blocker_id=user.id, blocked_id=blocked_user_id))
    lower_id, higher_id = sorted((user.id, blocked_user_id))
    Match.query.filter_by(first_user_id=lower_id, second_user_id=higher_id).delete()
    Like.query.filter(
        or_(
            (Like.liker_id == user.id) & (Like.liked_id == blocked_user_id),
            (Like.liker_id == blocked_user_id) & (Like.liked_id == user.id),
        )
    ).delete(synchronize_session=False)
    db.session.commit()
    return redirect(url_for("user.connections"))


@user_routes.route("/unmatch/<int:other_user_id>", methods=["POST"])
def unmatch_user(other_user_id):
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    if not users_are_matched(user.id, other_user_id):
        abort(404)
    lower_id, higher_id = sorted((user.id, other_user_id))
    Match.query.filter_by(first_user_id=lower_id, second_user_id=higher_id).delete()
    Like.query.filter(
        or_(
            (Like.liker_id == user.id) & (Like.liked_id == other_user_id),
            (Like.liker_id == other_user_id) & (Like.liked_id == user.id),
        )
    ).delete(synchronize_session=False)
    db.session.commit()
    return redirect(url_for("user.connections"))


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


@user_routes.route("/subscription/account")
def subscription_account():
    user = require_user()
    if user is None:
        return redirect(url_for("user.login"))
    return render_template(
        "user/pages/subscription_account.html",
        premium_subscription=active_subscription(user, "premium"),
        active_boost=active_subscription(user, "boost"),
        now_utc=datetime.utcnow(),
        subscription_history=Subscription.query.filter_by(user_id=user.id)
        .order_by(Subscription.created_at.desc())
        .limit(20)
        .all(),
    )


@user_routes.route("/subscription/checkout/<int:plan_id>", methods=["POST"])
def checkout_subscription(plan_id):
    user = require_user()
    if user is None:
        flash("Log in or create a free account before choosing a plan.", "info")
        return redirect(url_for("user.login"))
    plan = SubscriptionPlan.query.filter_by(
        id=plan_id,
        is_active=True,
    ).first()
    if plan is None or plan.plan_type not in {"premium", "boost"}:
        abort(404)
    if plan.amount_ngn <= 0 or plan.duration_days <= 0:
        current_app.logger.error("Invalid active subscription plan configuration: %s", plan.id)
        flash("This plan is temporarily unavailable. Please contact support.", "error")
        return redirect(url_for("root.subscription"))
    if not paystack_configuration_is_ready(current_app.config):
        flash("Online payments are not configured yet. Please contact support.", "error")
        return redirect(url_for("root.subscription"))

    reference = f"voveo_{user.id}_{secrets.token_urlsafe(24)}"
    purchase = Subscription(
        user_id=user.id,
        plan_name=plan.name,
        duration_days=plan.duration_days,
        amount_ngn=plan.amount_ngn,
        plan_type=plan.plan_type,
        status="pending",
        payment_provider="paystack",
        payment_reference=reference,
        payment_email=user.email.strip().lower(),
    )
    db.session.add(purchase)
    db.session.commit()

    try:
        response_data = paystack_request(
            "/transaction/initialize",
            {
                "email": purchase.payment_email,
                "amount": int(
                    (Decimal(purchase.amount_ngn) * 100).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                ),
                "currency": "NGN",
                "reference": reference,
                "callback_url": current_app.config["PAYSTACK_CALLBACK_URL"],
                "metadata": {
                    "subscription_id": purchase.id,
                    "plan_type": purchase.plan_type,
                },
            },
        )
    except RuntimeError as error:
        purchase.status = "failed"
        db.session.commit()
        flash(str(error), "error")
        return redirect(url_for("root.subscription"))

    authorization_url = (
        response_data.get("authorization_url")
        if isinstance(response_data, dict)
        else None
    )
    parsed_url = urlsplit(authorization_url or "")
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "checkout.paystack.com"
        or parsed_url.username
        or parsed_url.password
    ):
        purchase.status = "failed"
        db.session.commit()
        current_app.logger.error("Paystack returned an invalid checkout URL.")
        flash("Payment service could not start checkout. Please try again.", "error")
        return redirect(url_for("root.subscription"))
    return redirect(authorization_url, code=303)


@user_routes.route("/payments/paystack/callback")
def paystack_callback():
    user = require_user()
    if user is None:
        flash("Log in to confirm your payment and activate your purchase.", "info")
        return redirect(url_for("user.login"))
    reference = request.args.get("reference") or request.args.get("trxref")
    if not reference or len(reference) > 100:
        flash("We could not confirm the payment reference. Please check your plan status.", "error")
        return redirect(url_for("user.subscription_account"))
    purchase = Subscription.query.filter_by(
        payment_reference=reference,
        payment_provider="paystack",
        user_id=user.id,
    ).first()
    if purchase is None:
        abort(404)
    try:
        result = activate_verified_payment(reference)
    except RuntimeError:
        flash("Payment confirmation is temporarily unavailable. Your purchase will remain pending; please try again shortly.", "error")
        return redirect(url_for("user.subscription_account"))
    if result == "active":
        flash("Payment confirmed. Your one-time purchase is active.", "success")
    elif result == "pending":
        flash("Paystack is still processing the payment. Check back shortly.", "info")
    else:
        flash("We could not confirm this payment. Your paid features have not been activated.", "error")
    return redirect(url_for("user.subscription_account"))


@user_routes.route("/payments/paystack/webhook", methods=["POST"])
@csrf.exempt
def paystack_webhook():
    secret_key = current_app.config.get("PAYSTACK_SECRET_KEY")
    if not secret_key:
        abort(503)
    payload = request.get_data(cache=False)
    signature = request.headers.get("x-paystack-signature", "")
    expected_signature = hmac.new(
        secret_key.encode("utf-8"),
        payload,
        hashlib.sha512,
    ).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected_signature):
        abort(403)
    try:
        event = json.loads(payload)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        abort(400)
    if not isinstance(event, dict) or event.get("event") != "charge.success":
        return "", 200
    data = event.get("data")
    reference = data.get("reference") if isinstance(data, dict) else None
    if not isinstance(reference, str) or not reference or len(reference) > 100:
        abort(400)
    purchase_exists = Subscription.query.filter_by(
        payment_reference=reference,
        payment_provider="paystack",
    ).first()
    if purchase_exists is None:
        return "", 200
    try:
        result = activate_verified_payment(reference)
    except RuntimeError:
        return "", 503
    if result == "invalid":
        current_app.logger.error("Paystack webhook payment verification failed for reference %s", reference)
    return "", 200


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
        if reason not in REPORT_REASONS:
            return "Choose one of the available report reasons.", 400
        if len(details) > 4000:
            return "Report details must be 4000 characters or fewer.", 400
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
