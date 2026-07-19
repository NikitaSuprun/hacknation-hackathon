# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""CV ingestion gate: pointers only until legal sign-off.

Hack Nation participants disclose cvUrl for platform display, not VC
profiling; silver.person therefore stores the pointer only. Fetching and
LLM-parsing CV content stays behind the HACKNATION_CV_INGESTION env flag,
which is unset (disabled) by default - the fetch itself is deliberately
unimplemented until sign-off lands.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

CV_INGESTION_ENV: Final[str] = "HACKNATION_CV_INGESTION"
_TRUTHY: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})

STATUS_DISABLED: Final[str] = "disabled"
STATUS_NO_URL: Final[str] = "no_url"
STATUS_PENDING_SIGNOFF: Final[str] = "pending_signoff"


@dataclass(frozen=True, slots=True)
class CvFetchResult:
    """The typed outcome of one CV fetch attempt (no-op while gated)."""

    status: str
    cv_url: str | None
    detail: str


def cv_ingestion_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Whether CV content ingestion is switched on.

    Args:
        env: Environment mapping (os.environ by default).

    Returns:
        True only when HACKNATION_CV_INGESTION is set truthy.
    """
    mapping = os.environ if env is None else env
    return mapping.get(CV_INGESTION_ENV, "").strip().lower() in _TRUTHY


def fetch_cv(cv_url: str | None, *, enabled: bool) -> CvFetchResult:
    """Fetch one CV - a typed no-op while the legal gate is closed.

    Args:
        cv_url: The stored pointer (silver.person.cv_url).
        enabled: The resolved gate (see cv_ingestion_enabled).

    Returns:
        A disabled/no_url/pending_signoff result; never fetches today.
    """
    if not enabled:
        return CvFetchResult(
            status=STATUS_DISABLED,
            cv_url=cv_url,
            detail=f"{CV_INGESTION_ENV} not set; CV stored as pointer only",
        )
    if cv_url is None:
        return CvFetchResult(status=STATUS_NO_URL, cv_url=None, detail="person has no cv_url")
    return CvFetchResult(
        status=STATUS_PENDING_SIGNOFF,
        cv_url=cv_url,
        detail="live CV fetch/parse is not implemented pending legal sign-off",
    )
