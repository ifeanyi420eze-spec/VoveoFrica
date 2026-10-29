import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.engine import make_url
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from flask_socketio import SocketIO
from werkzeug.middleware.proxy_fix import ProxyFix


db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def create_app():
    # Read local development settings without overriding values supplied by the host.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

    app = Flask(__name__)
    app_env = os.environ.get("APP_ENV", "development").strip().lower()
    is_production = app_env == "production"
    if app_env not in {"development", "production", "testing"}:
        raise RuntimeError("APP_ENV must be development, testing, or production.")
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY must be set in the environment or .env file.")
    if is_production and len(secret_key) < 32:
        raise RuntimeError("Production SECRET_KEY must be at least 32 characters long.")
    app.config["SECRET_KEY"] = secret_key
    app.config["APP_ENV"] = app_env
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
    app.config["SESSION_COOKIE_SECURE"] = is_production
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_NAME"] = "voveofrica_session"
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 14
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True
    app.config["WTF_CSRF_SSL_STRICT"] = is_production
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600
    app.config["RATELIMIT_HEADERS_ENABLED"] = True
    app.config["LOG_LEVEL"] = os.environ.get("LOG_LEVEL", "INFO").upper()
    app.config["ADMIN_EMAILS"] = {
        email.strip().lower()
        for email in os.environ.get("ADMIN_EMAILS", "").split(",")
        if email.strip()
    }
    app.config["PROFILE_PHOTO_S3_BUCKET"] = os.environ.get(
        "PROFILE_PHOTO_S3_BUCKET", ""
    ).strip()
    app.config["AWS_REGION"] = os.environ.get("AWS_REGION", "").strip() or None
    app.config["PAYSTACK_SECRET_KEY"] = os.environ.get("PAYSTACK_SECRET_KEY")
    app.config["PAYSTACK_CALLBACK_URL"] = os.environ.get("PAYSTACK_CALLBACK_URL", "")
    app.config["SMTP_HOST"] = os.environ.get("SMTP_HOST", "")
    try:
        app.config["SMTP_PORT"] = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError as error:
        raise RuntimeError("SMTP_PORT must be a valid port number.") from error
    app.config["SMTP_USERNAME"] = os.environ.get("SMTP_USERNAME", "")
    app.config["SMTP_PASSWORD"] = os.environ.get("SMTP_PASSWORD", "")
    app.config["SMTP_FROM_EMAIL"] = os.environ.get("SMTP_FROM_EMAIL", "")
    app.config["SMTP_USE_TLS"] = os.environ.get("SMTP_USE_TLS", "true").lower() in {
        "1", "true", "yes"
    }
    redis_url = os.environ.get("REDIS_URL", "").strip()
    app.config["RATELIMIT_STORAGE_URI"] = os.environ.get(
        "RATELIMIT_STORAGE_URI", redis_url or "memory://"
    ).strip()
    socketio_cors_origins = os.environ.get("SOCKETIO_CORS_ALLOWED_ORIGINS", "").strip()
    if is_production:
        required_production_settings = {
            "SMTP_HOST": app.config["SMTP_HOST"],
            "SMTP_USERNAME": app.config["SMTP_USERNAME"],
            "SMTP_PASSWORD": app.config["SMTP_PASSWORD"],
            "SMTP_FROM_EMAIL": app.config["SMTP_FROM_EMAIL"],
            "PROFILE_PHOTO_S3_BUCKET": app.config["PROFILE_PHOTO_S3_BUCKET"],
            "AWS_REGION": app.config["AWS_REGION"],
            "ADMIN_EMAILS": app.config["ADMIN_EMAILS"],
        }
        missing_settings = [
            setting for setting, value in required_production_settings.items() if not value
        ]
        if missing_settings:
            raise RuntimeError(
                "Production configuration is missing required settings: "
                + ", ".join(missing_settings)
            )
        if app.config["PAYSTACK_SECRET_KEY"]:
            from pkg.payments import paystack_configuration_is_ready

            if not paystack_configuration_is_ready(app.config):
                raise RuntimeError(
                    "PAYSTACK_CALLBACK_URL must be a valid HTTPS callback when "
                    "PAYSTACK_SECRET_KEY is configured."
                )

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set in the environment or .env file.")
    if database_url.startswith("mysql://"):
        database_url = database_url.replace("mysql://", "mysql+pymysql://", 1)
    if not make_url(database_url).drivername.startswith("mysql"):
        raise RuntimeError("DATABASE_URL must use a MySQL-compatible driver.")
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    # Track schema changes with Alembic migrations instead of creating tables at startup.
    migrate.init_app(app, db)
    socketio_options = {
        "cors_allowed_origins": socketio_cors_origins or None,
        "logger": False,
        "engineio_logger": False,
    }
    if redis_url:
        socketio_options.update(
            message_queue=redis_url,
            channel="voveofrica",
        )
    socketio.init_app(app, **socketio_options)

    app.logger.setLevel(getattr(logging, app.config["LOG_LEVEL"], logging.INFO))
    if not any(isinstance(handler, logging.StreamHandler) for handler in app.logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s"
            )
        )
        app.logger.addHandler(handler)
    app.logger.info(
        "Application initialized (environment=%s, socketio_queue=%s)",
        app_env,
        "configured" if redis_url else "not configured",
    )

    from pkg.routes import root_routes
    from pkg.templates.user.routes import user_routes
    from pkg.templates.admin.routes import admin_routes
    from pkg import models

    app.register_blueprint(root_routes)
    app.register_blueprint(user_routes)
    app.register_blueprint(admin_routes)

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

    return app
