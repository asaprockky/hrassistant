"""Single trigger for candidate status changes.

A3 (email) and U5 (in-app notification) fan out from the same event: when a
candidate's status changes, we (a) insert a Notification row the user sees in
the app and (b) email the user if they have an address. Email failures never
block the status update — they are caught and reported back to the caller.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Candidate, Notification, User
from utils.mailer import EmailDeliveryError, send_email


class StatusChangeResult:
    """Outcome of the fan-out so endpoints can report mail status to the UI."""

    def __init__(self) -> None:
        self.notification_created: bool = False
        self.email_sent: bool = False
        self.email_error: Optional[str] = None


def _status_message(full_name: str, vacancy_name: Optional[str], status: str) -> tuple[str, str]:
    target = f' for "{vacancy_name}"' if vacancy_name else ""
    title = f"Application update: {status}"
    body = (
        f"Hello {full_name},\n\n"
        f"Your application{target} has moved to the \"{status}\" stage."
    )
    return title, body


def notify_candidate_status_change(
    db: Session,
    candidate: Candidate,
    new_status: str,
    *,
    user: Optional[User] = None,
    vacancy_name: Optional[str] = None,
) -> StatusChangeResult:
    """Insert a notification row and (best-effort) email the candidate.

    The caller is responsible for committing the surrounding transaction; the
    Notification row is added to the session here but not committed.
    """
    result = StatusChangeResult()
    user = user or candidate.user
    full_name = candidate.full_name or (
        f"{user.name} {user.surname}".strip() if user else "there"
    )

    title, body = _status_message(full_name, vacancy_name, new_status)

    notification = Notification(
        user_id=candidate.user_id,
        type="status_change",
        title=title,
        body=body,
        related_candidate_id=candidate.id,
        related_vacancy_id=candidate.vacancy_id,
        created_at=datetime.utcnow(),
    )
    db.add(notification)
    result.notification_created = True

    email = user.email if user else None
    if email:
        try:
            send_email(to_email=email, subject=title, plain_text=body)
            result.email_sent = True
        except EmailDeliveryError as exc:
            result.email_error = str(exc)
        except Exception as exc:  # never let mail break the status update
            result.email_error = str(exc)

    return result
