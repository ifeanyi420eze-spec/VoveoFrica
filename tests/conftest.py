import pytest

from app import app as application


@pytest.fixture
def app():
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application
