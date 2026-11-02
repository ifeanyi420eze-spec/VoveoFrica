from app import csrf, db, limiter


def create_app(config_overrides=None):
    from app import create_app as app_factory

    return app_factory(config_overrides)
