from io import BytesIO

from PIL import Image
import pytest

from app.utils.image_processor import process_profile_image
from app.routes.matches import _coordinate


def test_spatial_apis_require_a_signed_in_user(app):
    client = app.test_client()

    location_response = client.put(
        "/api/matches/location",
        json={"lat": 6.5244, "lon": 3.3792},
    )
    feed_response = client.get("/api/matches/feed")
    chat_response = client.post(
        "/api/chat/send",
        json={"other_user_id": 2, "text": "Hello"},
    )

    assert location_response.status_code == 401
    assert feed_response.status_code == 401
    assert chat_response.status_code == 401


def test_coordinate_validation_rejects_invalid_values():
    assert _coordinate("6.5244", "Latitude", -90, 90) == 6.5244
    assert _coordinate("-180", "Longitude", -180, 180) == -180

    for value in (True, "north", "NaN", "91"):
        with pytest.raises(ValueError):
            _coordinate(value, "Latitude", -90, 90)


def test_existing_page_route_endpoints_remain_registered(app):
    routes = {
        (rule.rule, method)
        for rule in app.url_map.iter_rules()
        for method in rule.methods
    }

    assert ("/register", "GET") in routes
    assert ("/register", "POST") in routes
    assert ("/profile", "GET") in routes
    assert ("/profile", "POST") in routes
    assert ("/payments/paystack/webhook", "POST") in routes
    assert ("/api/chat/send", "POST") in routes
    response = app.test_client().get("/about")
    assert response.status_code == 200
    assert app.test_client().get("/static/images/logo.png").status_code == 200


def test_profile_image_processor_resizes_and_encodes_webp():
    source = BytesIO()
    Image.new("RGB", (1600, 800), color="red").save(source, format="PNG")
    source.seek(0)

    processed = process_profile_image(source)

    image = Image.open(processed)
    assert image.format == "WEBP"
    assert image.size == (800, 400)
