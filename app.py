import os

from pkg import create_app, socketio


app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    socketio.run(
        app,
        debug=debug,
        use_reloader=debug,
        allow_unsafe_werkzeug=debug,
    )