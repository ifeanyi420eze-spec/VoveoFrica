from flask import session

from app import db
from app.models import User


def get_authenticated_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return db.session.get(User, user_id)
