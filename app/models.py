# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Frozen value objects for the app layer (WS-F)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """What one validated interview token grants access to."""

    outreach_id: str
    venture_id: str
    person_id: str
    thesis_id: str | None
    status: str
    expires_at: datetime | None
    questions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OutreachMail:
    """One rendered outbound email."""

    to_email: str
    subject: str
    body: str


@dataclass(frozen=True, slots=True)
class EmailContext:
    """Everything the compliant outreach email render needs."""

    to_email: str
    person_name: str
    venture_name: str
    source_note: str
    interview_url: str
    opt_out_url: str


@dataclass(frozen=True, slots=True)
class OutreachRequest:
    """One outreach send as requested by the API layer."""

    venture_id: str
    thesis_id: str | None
    base_url: str
    actor: str


@dataclass(frozen=True, slots=True)
class OutreachTransition:
    """One state-machine step applied to an outreach row."""

    status: str
    actor: str
    now: datetime
    consent_at: datetime | None


@dataclass(frozen=True, slots=True)
class OutreachResult:
    """Outcome of one outreach send: the stored row plus the raw token."""

    outreach_id: str
    token: str
    interview_url: str
    to_email: str
    status: str
