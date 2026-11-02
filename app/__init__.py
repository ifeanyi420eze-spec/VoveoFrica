import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix


db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def create_app(config_overrides=None):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

    app = Flask(__name__)
    overrides = config_overrides or {}
    app_env = str(overrides.get("APP_ENV", os.environ.get("APP_ENV", "development")))
    app_env = app_env.strip().lower()
    if app_env not in {"development", "production", "testing"}:
        raise RuntimeError("APP_ENV must be development, testing, or production.")
    is_production = app_env == "production"
    is_testing = app_env == "testing"

    secret_key = overrides.get("SECRET_KEY") or os.environ.get("SECRET_KEY")
    if not secret_key and is_testing:
        secret_key = "test-only-secret-key"
    if not secret_key:
        raise RuntimeError("SECRET_KEY must be set in the environment or .env file.")
    if is_production and len(secret_key) < 32:
        raise RuntimeError("Production SECRET_KEY must be at least 32 characters long.")
    try:
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError as error:
        raise RuntimeError("SMTP_PORT must be a valid port number.") from error

    app.config.update(
        SECRET_KEY=secret_key,
        APP_ENV=app_env,
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        SESSION_COOKIE_SECURE=is_production,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_NAME="voveofrica_session",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,
        SESSION_REFRESH_EACH_REQUEST=True,
        WTF_CSRF_SSL_STRICT=is_production,
        WTF_CSRF_TIME_LIMIT=3600,
        RATELIMIT_HEADERS_ENABLED=True,
        LOG_LEVEL=os.environ.get("LOG_LEVEL", "INFO").upper(),
        ADMIN_EMAILS={
            email.strip().lower()
            for email in os.environ.get("ADMIN_EMAILS", "").split(",")
            if email.strip()
        },
        PROFILE_PHOTO_S3_BUCKET=os.environ.get("PROFILE_PHOTO_S3_BUCKET", "").strip(),
        AWS_REGION=os.environ.get("AWS_REGION", "").strip() or None,
        R2_ENDPOINT_URL=os.environ.get("R2_ENDPOINT_URL", "").strip(),
        R2_ACCESS_KEY_ID=os.environ.get("R2_ACCESS_KEY_ID", "").strip(),
        R2_SECRET_ACCESS_KEY=os.environ.get("R2_SECRET_ACCESS_KEY", "").strip(),
        R2_BUCKET_NAME=os.environ.get("R2_BUCKET_NAME", "").strip(),
        PUSHER_APP_ID=os.environ.get("PUSHER_APP_ID", "").strip(),
        PUSHER_KEY=os.environ.get("PUSHER_KEY", "").strip(),
        PUSHER_SECRET=os.environ.get("PUSHER_SECRET", "").strip(),
        PUSHER_CLUSTER=os.environ.get("PUSHER_CLUSTER", "").strip(),
        PAYSTACK_SECRET_KEY=os.environ.get("PAYSTACK_SECRET_KEY"),
        PAYSTACK_CALLBACK_URL=os.environ.get("PAYSTACK_CALLBACK_URL", ""),
        SMTP_HOST=os.environ.get("SMTP_HOST", ""),
        SMTP_PORT=smtp_port,
        SMTP_USERNAME=os.environ.get("SMTP_USERNAME", ""),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD", ""),
        SMTP_FROM_EMAIL=os.environ.get("SMTP_FROM_EMAIL", ""),
        SMTP_USE_TLS=os.environ.get("SMTP_USE_TLS", "true").lower()
        in {"1", "true", "yes"},
        RATELIMIT_STORAGE_URI=os.environ.get(
            "RATELIMIT_STORAGE_URI",
            os.environ.get("REDIS_URL", "").strip() or "memory://",
        ).strip(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    database_url = overrides.get("SQLALCHEMY_DATABASE_URI") or os.environ.get(
        "DATABASE_URL"
    )
    if not database_url:
        if is_testing:
            database_url = "sqlite:///:memory:"
        else:
            raise RuntimeError("DATABASE_URL must be set in the environment or .env file.")
    if not is_testing:
        try:
            drivername = make_url(database_url).drivername
        except (ArgumentError, TypeError, ValueError) as error:
            raise RuntimeError("DATABASE_URL must be a valid PostgreSQL URL.") from error
        if not drivername.startswith("postgresql"):
            raise RuntimeError("DATABASE_URL must use a PostgreSQL-compatible driver.")
        if drivername == "postgresql":
            database_url = database_url.replace(
                "postgresql://", "postgresql+psycopg2://", 1
            )
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config.update(overrides)

    if is_production:
        required_settings = {
            "SMTP_HOST": app.config["SMTP_HOST"],
            "SMTP_USERNAME": app.config["SMTP_USERNAME"],
            "SMTP_PASSWORD": app.config["SMTP_PASSWORD"],
            "SMTP_FROM_EMAIL": app.config["SMTP_FROM_EMAIL"],
            "R2_ENDPOINT_URL": app.config["R2_ENDPOINT_URL"],
            "R2_ACCESS_KEY_ID": app.config["R2_ACCESS_KEY_ID"],
            "R2_SECRET_ACCESS_KEY": app.config["R2_SECRET_ACCESS_KEY"],
            "R2_BUCKET_NAME": app.config["R2_BUCKET_NAME"],
            "PUSHER_APP_ID": app.config["PUSHER_APP_ID"],
            "PUSHER_KEY": app.config["PUSHER_KEY"],
            "PUSHER_SECRET": app.config["PUSHER_SECRET"],
            "PUSHER_CLUSTER": app.config["PUSHER_CLUSTER"],
            "ADMIN_EMAILS": app.config["ADMIN_EMAILS"],
        }
        missing_settings = [
            setting for setting, value in required_settings.items() if not value
        ]
        if missing_settings:
            raise RuntimeError(
                "Production configuration is missing required settings: "
                + ", ".join(missing_settings)
            )
        if app.config["PAYSTACK_SECRET_KEY"]:
            from app.services.payments import paystack_configuration_is_ready

            if not paystack_configuration_is_ready(app.config):
                raise RuntimeError(
                    "PAYSTACK_CALLBACK_URL must be a valid HTTPS callback when "
                    "PAYSTACK_SECRET_KEY is configured."
                )

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    migrate.init_app(app, db)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    app.logger.setLevel(getattr(logging, app.config["LOG_LEVEL"], logging.INFO))
    if not any(isinstance(handler, logging.StreamHandler) for handler in app.logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        app.logger.addHandler(handler)

    from app import models
    from app.routes.chat import chat_bp
    from app.routes.matches import matches_bp
    from app.routes.admin import admin_routes
    from app.routes.pages import root_routes
    from app.routes.user import user_routes

    _ = models

    app.register_blueprint(root_routes)
    app.register_blueprint(user_routes)
    app.register_blueprint(admin_routes)
    app.register_blueprint(matches_bp, url_prefix="/api/matches")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")

    if is_production:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    @app.errorhandler(404)
    def page_not_found(_error):
        return render_template("error_pages/404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(_error):
        return render_template("error_pages/500.html"), 500

    @app.errorhandler(413)
    def request_entity_too_large(_error):
        return render_template("error_pages/413.html"), 413

    @app.get("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            app.logger.exception("Health check database probe failed")
            return {"status": "unhealthy", "database": "unavailable"}, 503
        return {"status": "ok", "database": "ok"}, 200

    app.logger.info("Application initialized (environment=%s)", app_env)
    return app
