import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional


class EmailDeliveryError(RuntimeError):
    """Raised when SMTP configuration or delivery fails."""


def _smtp_settings() -> dict:
    login = os.getenv("SMTP_LOGIN", "")
    return {
        "server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "465")),
        "login": login,
        "password": os.getenv("SMTP_APP_PASSWORD", ""),
        "sender": os.getenv("SENDER_EMAIL", login),
    }


def send_email(
    to_email: str,
    subject: str,
    plain_text: str,
    html: Optional[str] = None,
) -> None:
    settings = _smtp_settings()
    if not settings["login"] or not settings["password"] or not settings["sender"]:
        raise EmailDeliveryError(
            "SMTP_LOGIN, SMTP_APP_PASSWORD, and SENDER_EMAIL must be configured."
        )

    message = EmailMessage()
    message["From"] = settings["sender"]
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(plain_text)

    if html:
        message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(
            settings["server"],
            settings["port"],
            context=context,
            timeout=20,
        ) as smtp:
            smtp.login(settings["login"], settings["password"])
            smtp.send_message(message)
    except Exception as exc:
        raise EmailDeliveryError(str(exc)) from exc
