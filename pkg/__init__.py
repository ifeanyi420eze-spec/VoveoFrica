import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.engine import make_url
from flask_socketio import SocketIO


db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()


def create_app():
    # Read local development settings without overriding values supplied by the host.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

    app = Flask(__name__)
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY must be set in the environment or .env file.")
    app.config["SECRET_KEY"] = secret_key

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
    # Track schema changes with Alembic migrations instead of creating tables at startup.
    migrate.init_app(app, db)
    socketio.init_app(app)

    from pkg.routes import root_routes
    from pkg.templates.user.routes import user_routes
    from pkg.templates.admin.routes import admin_routes
    from pkg import models

    app.register_blueprint(root_routes)
    app.register_blueprint(user_routes)
    app.register_blueprint(admin_routes)

    return app
