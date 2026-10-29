import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


class EmailAuthConfigurationError(RuntimeError):
    pass


class EmailAuthDeliveryError(RuntimeError):
    pass


def send_email_code(recipient, code, purpose):
    host = current_app.config.get("SMTP_HOST")
    sender = current_app.config.get("SMTP_FROM_EMAIL")
    if not host or not sender:
        raise EmailAuthConfigurationError(
            "Email verification is not configured. Contact the site administrator."
        )

    port = current_app.config["SMTP_PORT"]
    username = current_app.config.get("SMTP_USERNAME")
    password = current_app.config.get("SMTP_PASSWORD")
    use_tls = current_app.config["SMTP_USE_TLS"]
    if bool(username) != bool(password):
        raise EmailAuthConfigurationError(
            "Email verification is not configured. Contact the site administrator."
        )

    purpose_text = "verify your email address" if purpose == "registration" else "sign in"
    message = EmailMessage()
    message["Subject"] = "Your VOVEOFRICA verification code"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        f"Use this code to {purpose_text}: {code}\n\n"
        "The code expires in 10 minutes and can only be used once. "
        "If you did not request it, you can ignore this email."
    )

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if use_tls:
                smtp.starttls(context=ssl.create_default_context())
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise EmailAuthDeliveryError(
            "We could not send your verification email. Please try again."
        ) from error
