from decimal import Decimal, InvalidOperation

from flask import Blueprint, request
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_Distance, ST_MakePoint, ST_SetSRID
from sqlalchemy import cast, func
from sqlalchemy.exc import SQLAlchemyError

from app import db, limiter
from app.models import Block, Profile
from app.routes.auth import get_authenticated_user


matches_bp = Blueprint("matches", __name__)


def _coordinate(value, name, minimum, maximum):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number in range {minimum} to {maximum}.")
    try:
        coordinate = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number in range {minimum} to {maximum}.") from error
    if not coordinate.is_finite() or not minimum <= coordinate <= maximum:
        raise ValueError(f"{name} must be a number in range {minimum} to {maximum}.")
    return float(coordinate)


def _location_point(longitude, latitude):
    return ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)


@matches_bp.put("/location")
@limiter.limit("30 per minute")
def update_location():
    user = get_authenticated_user()
    if user is None:
        return {"error": "You must be logged in to update your location."}, 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "A JSON object with latitude and longitude is required."}, 400
    try:
        latitude = _coordinate(data.get("lat"), "Latitude", -90, 90)
        longitude = _coordinate(data.get("lon"), "Longitude", -180, 180)
    except ValueError as error:
        return {"error": str(error)}, 400

    profile = Profile.query.filter_by(user_id=user.id).first()
    if profile is None:
        profile = Profile(user_id=user.id)
        db.session.add(profile)
    profile.location = _location_point(longitude, latitude)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return {"status": "updated"}, 200


@matches_bp.get("/feed")
def get_discovery_feed():
    user = get_authenticated_user()
    if user is None:
        return {"error": "You must be logged in to view nearby profiles."}, 401

    raw_distance = request.args.get("distance_meters", "25000")
    try:
        max_distance_meters = int(raw_distance)
    except (TypeError, ValueError):
        return {"error": "distance_meters must be a positive integer."}, 400
    if not 1 <= max_distance_meters <= 200_000:
        return {"error": "distance_meters must be between 1 and 200000."}, 400

    own_profile = Profile.query.filter_by(user_id=user.id).first()
    if own_profile is None or own_profile.location is None:
        return {"error": "Set your location before viewing nearby profiles."}, 409

    user_location = cast(own_profile.location, Geography(srid=4326))
    candidate_location = cast(Profile.location, Geography(srid=4326))
    blocked_ids = db.session.query(Block.blocked_id).filter(
        Block.blocker_id == user.id
    )
    blocking_ids = db.session.query(Block.blocker_id).filter(
        Block.blocked_id == user.id
    )
    profiles = (
        Profile.query.filter(
            Profile.user_id != user.id,
            Profile.location.is_not(None),
            func.ST_DWithin(
                candidate_location,
                user_location,
                max_distance_meters,
            ),
            ~Profile.user_id.in_(blocked_ids),
            ~Profile.user_id.in_(blocking_ids),
        )
        .order_by(ST_Distance(candidate_location, user_location))
        .limit(100)
        .all()
    )
    return {"profiles": [profile.id for profile in profiles]}, 200
