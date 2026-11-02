from pusher import Pusher
from pusher.errors import PusherError
from requests.exceptions import RequestException
from flask import current_app


class RealtimeDeliveryError(RuntimeError):
    pass


def get_pusher_client():
    config = current_app.config
    settings = {
        "app_id": config.get("PUSHER_APP_ID"),
        "key": config.get("PUSHER_KEY"),
        "secret": config.get("PUSHER_SECRET"),
        "cluster": config.get("PUSHER_CLUSTER"),
    }
    if not all(settings.values()):
        raise RuntimeError("Pusher real-time messaging is not configured.")
    return Pusher(**settings, ssl=True)


def conversation_channel(sender_id, receiver_id):
    return f"private-chat-{min(sender_id, receiver_id)}-{max(sender_id, receiver_id)}"


def broadcast_message(sender_id, receiver_id, message_text, payload=None):
    event_data = payload or {
        "sender_id": sender_id,
        "message": message_text,
    }
    try:
        client = get_pusher_client()
        client.trigger(
            conversation_channel(sender_id, receiver_id),
            "new-message",
            event_data,
        )
    except (PusherError, RequestException, RuntimeError) as error:
        current_app.logger.exception("Pusher message broadcast failed")
        raise RealtimeDeliveryError("Pusher could not deliver the message event.") from error


def broadcast_event(sender_id, receiver_id, event_name, payload):
    try:
        get_pusher_client().trigger(
            conversation_channel(sender_id, receiver_id),
            event_name,
            payload,
        )
    except (PusherError, RequestException, RuntimeError) as error:
        current_app.logger.exception("Pusher event broadcast failed")
        raise RealtimeDeliveryError("Pusher could not deliver the event.") from error


def authorize_channel(channel_name, socket_id):
    try:
        return get_pusher_client().authenticate(channel_name, socket_id)
    except (PusherError, RequestException, RuntimeError) as error:
        current_app.logger.exception("Pusher channel authorization failed")
        raise RealtimeDeliveryError("Pusher could not authorize the channel.") from error
