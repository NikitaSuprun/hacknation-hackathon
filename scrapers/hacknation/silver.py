# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Hack Nation project payloads to silver.project rows.

silver.project was born GitHub-shaped; Hack Nation projects join it as
first-class rows (source_platform='hacknation') with the repo columns NULL and
the pitch/event columns filled - one table keeps venture anchoring and the D8
repo auto-merge trivial. The emitted column set mirrors schemas/ddl/20_silver.sql
exactly; tests pin it against the DDL registry.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Final, cast

from contracts.models import Json, SinkRow, SinkValue
from tools import ids, norm

SOURCE_PLATFORM: Final[str] = "hacknation"


class MalformedProjectPayloadError(ValueError):
    """Raised when a project payload is not an object carrying an id."""

    def __init__(self) -> None:
        """Fixed message; the id is the only hard requirement."""
        super().__init__("hacknation project payload needs an object with an 'id'")


def project_row(
    payload: Json,
    *,
    source_url: str,
    scraped_at: datetime,
    updated_at: datetime,
) -> SinkRow:
    """Render one Hack Nation project payload as a full silver.project row.

    Args:
        payload: The bronze VARIANT payload (bff-projects-public-v2 object).
        source_url: The bronze row's source_url.
        scraped_at: The bronze row's scrape time (tz-aware).
        updated_at: Silver write time (tz-aware).

    Returns:
        A row containing every silver.project column; GitHub-only columns NULL.

    Raises:
        MalformedProjectPayloadError: If the payload is not an object with an id.
    """
    if not isinstance(payload, dict):
        raise MalformedProjectPayloadError
    project_key = _key_text(payload.get("id"))
    if project_key is None:
        raise MalformedProjectPayloadError
    structured = payload.get("structured")
    github_raw = _text(payload.get("githubUrl"))
    return {
        "project_id": ids.hacknation_project_id(project_key),
        "repo_id": None,
        "full_name": None,
        "name": _text(payload.get("title")),
        "owner_login": None,
        "is_org_owned": None,
        "description": _text(payload.get("summary")),
        "summary_ai": None,
        "market_tags": _string_list(payload.get("tags")),
        "usp_notes": _text(structured.get("usp")) if isinstance(structured, dict) else None,
        "primary_language": None,
        "languages": None,
        "topics": _string_list(payload.get("techStack")),
        "stars": None,
        "forks": None,
        "license": None,
        "homepage_url": _text(payload.get("demoUrl")),
        "source_platform": SOURCE_PLATFORM,
        # Normalized at ingest so the D8 repo auto-merge is plain equality.
        "github_url": norm.url_norm(github_raw) if github_raw is not None else None,
        "structured": _structured(structured),
        "event_title": _text(payload.get("eventTitle")),
        "challenge_title": _text(payload.get("challengeTitle")),
        "is_winner": _bool_or_none(payload.get("winner")),
        "arxiv_ids_in_readme": None,
        "funding_signals": None,
        "is_corporate_oss": None,
        "is_academic": None,
        "venture_likeness": None,
        "contributor_count": _contributor_count(payload),
        "created_at_source": _created_at(payload.get("createdAt")),
        "pushed_at": None,
        "ai_model_version": None,
        "source_url": source_url,
        "scraped_at": scraped_at,
        "updated_at": updated_at,
    }


def _text(value: Json) -> str | None:
    """Stripped string; '' and whitespace count as absent."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _key_text(value: Json) -> str | None:
    """Project keys as strings, tolerating JSON number ids (bool is not a key)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    return _text(value)


def _string_list(value: Json) -> list[SinkValue]:
    """String items of a JSON list; anything else is an empty list."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _bool_or_none(value: Json) -> bool | None:
    """Booleans pass through; anything else is unknown."""
    return value if isinstance(value, bool) else None


def _structured(value: Json) -> SinkValue:
    """The pitch object passes through as VARIANT; anything else is NULL."""
    if not isinstance(value, dict):
        return None
    # Json is a semantic subset of SinkValue; the cast bridges the container
    # invariance the type system cannot see through (tools.ddl_registry does
    # the same).
    return cast("SinkValue", value)


def _contributor_count(payload: Mapping[str, Json]) -> int | None:
    """Team size plus the author; None when the payload names neither."""
    team = payload.get("team")
    team_size = len(team) if isinstance(team, list) else None
    if isinstance(payload.get("authorProfile"), dict):
        return (team_size or 0) + 1
    return team_size


def _created_at(value: Json) -> datetime | None:
    """The createdAt string as a tz-aware datetime; naive pins to UTC, junk is None."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
