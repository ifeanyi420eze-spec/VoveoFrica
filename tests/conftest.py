import pytest

from app import create_app


@pytest.fixture
def app():
    application = create_app(
        {
            "APP_ENV": "testing",
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    yield application
