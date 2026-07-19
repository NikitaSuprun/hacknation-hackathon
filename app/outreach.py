# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Consent-based outreach: compliant email render, suppression, state machine.

Every send is preceded by a suppression check (ops.erasure_suppression plus
opted-out outreach rows), the email discloses who we are, why we reached out
and which public data we saw, and it carries a one-click opt-out link. Only
the sha256 of the single-use interview token is stored.
"""

import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Final, Protocol

import httpx

from app.models import (
    EmailContext,
    OutreachMail,
    OutreachRequest,
    OutreachResult,
    OutreachTransition,
)
from app.store import VIEW_VENTURE_TEAM, DataStore
from contracts.models import Json, SinkRow
from scoring.snapshot import get_float
from scrapers.common.jsonutil import as_mapping, as_sink, get_str

FUND_NAME: Final[str] = "Maschmeyer's Chosen Portfolio"
SENDER_EMAIL: Final[str] = "partners@chosen-portfolio.example"
TOKEN_TTL_DAYS: Final[int] = 14
TOKEN_BYTES: Final[int] = 16
RESEND_API_URL: Final[str] = "https://api.resend.com/emails"
RESEND_TIMEOUT_SECONDS: Final[float] = 30.0

OUTREACH_STATUSES: Final[tuple[str, ...]] = (
    "draft",
    "approved",
    "sent",
    "bounced",
    "replied",
    "consented",
    "declined",
    "interview_scheduled",
    "interview_started",
    "interviewed",
    "closed",
    "opted_out",
    "expired",
)

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


class UnknownVentureError(LookupError):
    """The venture id names no gold.venture row."""

    def __init__(self, venture_id: str) -> None:
        """Name the missing venture."""
        super().__init__(f"no venture {venture_id}")


class MissingContactError(LookupError):
    """No team member with a usable email address was found."""

    def __init__(self, venture_id: str) -> None:
        """Name the venture without contactable members."""
        super().__init__(f"no contactable founder for venture {venture_id}")


class SuppressedPersonError(PermissionError):
    """The person is erasure-suppressed or has opted out of contact."""

    def __init__(self, person_id: str) -> None:
        """Name the suppressed person."""
        super().__init__(f"person {person_id} is suppressed; no outreach allowed")


class MailSendError(RuntimeError):
    """The mail backend refused the send."""

    def __init__(self, status: int) -> None:
        """Carry the HTTP status in the message."""
        super().__init__(f"mail send failed with HTTP {status}")


class Mailer(Protocol):
    """The one outbound-email seam (Resend live, recording in fixtures/tests)."""

    def send(self, mail: OutreachMail) -> None:
        """Deliver one rendered email."""
        ...


class RecordingMailer:
    """Captures sends in memory; the fixtures-mode and test mailer."""

    def __init__(self) -> None:
        """Start with nothing sent."""
        self.sent: Final[list[OutreachMail]] = []

    def send(self, mail: OutreachMail) -> None:
        """Record the mail instead of delivering it.

        Args:
            mail: The rendered email.
        """
        self.sent.append(mail)


class ResendHttpMailer:
    """Live delivery through the Resend HTTP API."""

    def __init__(
        self,
        api_key: str,
        *,
        sender: str = SENDER_EMAIL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Bind credentials; a transport replays canned responses in tests."""
        self._sender: Final[str] = sender
        self._client: Final[httpx.Client] = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=RESEND_TIMEOUT_SECONDS,
        )

    def send(self, mail: OutreachMail) -> None:
        """POST the email to Resend.

        Args:
            mail: The rendered email.

        Raises:
            MailSendError: On any non-2xx response.
        """
        response = self._client.post(
            RESEND_API_URL,
            json={
                "from": self._sender,
                "to": [mail.to_email],
                "subject": mail.subject,
                "text": mail.body,
            },
        )
        if not response.is_success:
            raise MailSendError(response.status_code)


def mint_token() -> str:
    """A fresh single-use interview token.

    Returns:
        A 32-hex-char secret.
    """
    return secrets.token_hex(TOKEN_BYTES)


def token_hash(token: str) -> str:
    """The stored form of an interview token.

    Args:
        token: The raw token.

    Returns:
        Its sha256 hex digest.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def append_history(history: Json, state: str, actor: str, now: datetime) -> list[Json]:
    """A history array extended with one state transition.

    Args:
        history: The prior history value (may be None).
        state: The new outreach status.
        actor: Who caused the transition.
        now: The transition timestamp.

    Returns:
        The extended history list.
    """
    entries: list[Json] = list(history) if isinstance(history, list) else []
    entries.append({"state": state, "ts": now.isoformat(), "actor": actor})
    return entries


def _suppressed_source_keys(store: DataStore) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for row in store.rows("ops.erasure_suppression"):
        source = get_str(row, "source")
        key_hash = get_str(row, "source_key_hash")
        if source is not None and key_hash is not None:
            pairs.add((source, key_hash))
    return pairs


def _person_source_pairs(store: DataStore, person_id: str) -> set[tuple[str, str]]:
    record_ids = {
        get_str(row, "source_record_id")
        for row in store.rows("silver.person_source_link")
        if row.get("person_id") == person_id and row.get("status") == "active"
    }
    pairs: set[tuple[str, str]] = set()
    for row in store.rows("silver.person_source_record"):
        source = get_str(row, "source")
        key = get_str(row, "source_key")
        if row.get("source_record_id") in record_ids and source is not None and key is not None:
            pairs.add((source, hashlib.sha256(key.encode("utf-8")).hexdigest()))
    return pairs


def is_suppressed(store: DataStore, person_id: str) -> bool:
    """Whether contacting this person is forbidden.

    True when any outreach row for the person is opted_out, or any of the
    person's active source identities appears in ops.erasure_suppression.

    Args:
        store: The data seam.
        person_id: The person to check.

    Returns:
        True when the person must not be contacted.
    """
    for row in store.rows("gold.outreach"):
        if row.get("person_id") == person_id and row.get("status") == "opted_out":
            return True
    suppressed = _suppressed_source_keys(store)
    return bool(suppressed & _person_source_pairs(store, person_id))


def render_email(context: EmailContext) -> OutreachMail:
    """The compliance-complete outreach email.

    Args:
        context: Recipient, venture, data-source note, and the two links.

    Returns:
        The rendered mail: sender identity, why contacted, data sources,
        privacy note, and the one-click opt-out.
    """
    subject = f"{FUND_NAME}: your work on {context.venture_name}"
    body = (
        f"Hi {context.person_name},\n\n"
        f"I'm writing from {FUND_NAME}, an early-stage venture fund. "
        f"We came across {context.source_note}, and we'd love to learn more "
        f"about {context.venture_name} directly from you.\n\n"
        "If you're open to it, this link starts a short, consent-based "
        f"AI-assisted interview (about 10 minutes):\n{context.interview_url}\n\n"
        "Why you're receiving this: we source from public data only "
        "(GitHub, arXiv/OpenAlex, the Zefix commercial register). Nothing "
        "you share is used without your explicit consent on the first "
        "screen, and you can request erasure at any time.\n\n"
        "Prefer not to hear from us again? One click opts you out:\n"
        f"{context.opt_out_url}\n\n"
        f"Best regards,\n{FUND_NAME}\n{SENDER_EMAIL}"
    )
    return OutreachMail(to_email=context.to_email, subject=subject, body=body)


def _venture_row(store: DataStore, venture_id: str) -> dict[str, Json]:
    for row in store.rows("gold.venture"):
        if row.get("venture_id") == venture_id:
            return row
    raise UnknownVentureError(venture_id)


def _pick_founder(store: DataStore, venture_id: str) -> dict[str, Json]:
    team = [row for row in store.rows(VIEW_VENTURE_TEAM) if row.get("venture_id") == venture_id]
    team.sort(
        key=lambda row: (row.get("is_founder_guess") is True, get_float(row, "weight") or 0.0),
        reverse=True,
    )
    persons = {row.get("person_id"): row for row in store.rows("silver.person")}
    for member in team:
        person = as_mapping(persons.get(member.get("person_id")))
        email = get_str(person, "primary_email")
        if email is not None:
            picked = dict(member)
            picked["to_email"] = email
            return picked
    raise MissingContactError(venture_id)


def _question_plan(store: DataStore, venture_id: str) -> list[str]:
    gaps = [row for row in store.rows("gold.venture_gaps") if row.get("venture_id") == venture_id]
    gaps.sort(key=lambda row: get_float(row, "importance") or 0.0, reverse=True)
    return [text for row in gaps if (text := get_str(row, "question_text")) is not None]


def _source_note(founder: dict[str, Json], venture: dict[str, Json]) -> str:
    venture_name = get_str(venture, "name") or "your venture"
    note = f"your public work on {venture_name}"
    login = get_str(founder, "github_login")
    if login is not None:
        note = f"your GitHub profile @{login} and {note}"
    website = get_str(venture, "website_url")
    if website is not None:
        note = f"{note} ({website})"
    return note


def send_outreach(
    store: DataStore,
    mailer: Mailer,
    request: OutreachRequest,
    *,
    clock: Clock,
    id_factory: IdFactory,
) -> OutreachResult:
    """Mint a token, render the compliant email, send it, persist the row.

    The stored row carries only the token's sha256; the raw token exists in
    the email body (and the returned result, so the fixtures demo can open
    the interview without a real inbox).

    Args:
        store: The data seam.
        mailer: The outbound-email seam.
        request: The venture, thesis, link origin, and acting user.
        clock: Injected time source.
        id_factory: Injected id source.

    Returns:
        The persisted outreach identifiers plus the raw token.

    Raises:
        SuppressedPersonError: If the person opted out or is erasure-suppressed.
    """
    venture = _venture_row(store, request.venture_id)
    founder = _pick_founder(store, request.venture_id)
    person_id = get_str(founder, "person_id") or ""
    if is_suppressed(store, person_id):
        raise SuppressedPersonError(person_id)
    now = clock()
    token = mint_token()
    interview_url = f"{request.base_url}/#/interview/{token}"
    to_email = get_str(founder, "to_email") or ""
    mail = render_email(
        EmailContext(
            to_email=to_email,
            person_name=get_str(founder, "full_name") or "there",
            venture_name=get_str(venture, "name") or "your venture",
            source_note=_source_note(founder, venture),
            interview_url=interview_url,
            opt_out_url=f"{request.base_url}/v1/optout/{token}",
        )
    )
    history = append_history(None, "draft", request.actor, now)
    mailer.send(mail)
    history = append_history(history, "sent", request.actor, now)
    outreach_id = id_factory()
    row: SinkRow = {
        "outreach_id": outreach_id,
        "venture_id": request.venture_id,
        "thesis_id": request.thesis_id,
        "person_id": person_id,
        "channel": "email",
        "to_email": to_email,
        "subject": mail.subject,
        "body": mail.body,
        "token_hash": token_hash(token),
        "token_expires_at": now + timedelta(days=TOKEN_TTL_DAYS),
        "question_plan": as_sink({"questions": list(_question_plan(store, request.venture_id))}),
        "status": "sent",
        "consent_at": None,
        "sent_at": now,
        "last_event_at": now,
        "history": as_sink(history),
        "created_by": request.actor,
        "updated_at": now,
    }
    store.upsert("gold.outreach", [row])
    return OutreachResult(
        outreach_id=outreach_id,
        token=token,
        interview_url=interview_url,
        to_email=to_email,
        status="sent",
    )


def transition_outreach(
    store: DataStore, outreach_row: dict[str, Json], step: OutreachTransition
) -> dict[str, Json]:
    """Move one outreach row to a new status, appending to its history.

    Args:
        store: The data seam.
        outreach_row: The current row (as read from the store).
        step: The transition: target status, actor, timestamp, consent.

    Returns:
        The updated row as stored.

    Raises:
        ValueError: If the status is not part of the DDL state machine.
    """
    if step.status not in OUTREACH_STATUSES:
        raise ValueError(step.status)
    updated = dict(outreach_row)
    updated["status"] = step.status
    updated["last_event_at"] = step.now.isoformat()
    updated["updated_at"] = step.now.isoformat()
    if step.consent_at is not None:
        updated["consent_at"] = step.consent_at.isoformat()
    updated["history"] = append_history(
        outreach_row.get("history"), step.status, step.actor, step.now
    )
    store.upsert("gold.outreach", [{key: as_sink(value) for key, value in updated.items()}])
    return updated
