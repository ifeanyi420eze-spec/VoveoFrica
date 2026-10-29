from pkg import email_auth


def test_send_email_code_uses_tls_and_sends_message(app, monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            calls.append(("close",))

        def starttls(self, context):
            calls.append(("starttls", context is not None))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send", message["To"], message["Subject"], message.get_content()))

    monkeypatch.setattr(email_auth.smtplib, "SMTP", FakeSMTP)
    with app.app_context():
        email_auth.send_email_code("recipient@example.com", "123456", "login")

    assert calls[0] == ("connect", app.config["SMTP_HOST"], app.config["SMTP_PORT"], 10)
    assert calls[1] == ("starttls", True)
    assert calls[2][0] == "login"
    assert calls[3][0:3] == (
        "send",
        "recipient@example.com",
        "Your VOVEOFRICA verification code",
    )
    assert "123456" in calls[3][3]


def test_health_endpoint_reports_database(app):
    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "ok"}
