from urllib.parse import urlsplit


def paystack_configuration_is_ready(config):
    callback_url = config.get("PAYSTACK_CALLBACK_URL", "")
    try:
        parsed_url = urlsplit(callback_url)
        callback_port = parsed_url.port
    except ValueError:
        return False
    return bool(config.get("PAYSTACK_SECRET_KEY")) and (
        parsed_url.scheme == "https"
        and parsed_url.hostname
        and callback_port in (None, 443)
        and parsed_url.path == "/payments/paystack/callback"
        and not parsed_url.username
        and not parsed_url.password
        and not parsed_url.query
        and not parsed_url.fragment
    )
