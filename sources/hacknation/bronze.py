# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Pure row-builders shaping Hack Nation payloads into the bronze envelope.

No I/O happens here — the CLI fetches bodies and owns every sink write — so
each builder is a plain function from response body to rows matching
schemas/ddl/10_bronze.sql exactly, with payloads stored verbatim.
"""

from datetime import datetime
from typing import Final, cast

from contracts.models import Json, SinkRow, SinkValue
from sources.hacknation.client import DEFAULT_PEOPLE_LIMIT, PEOPLE_URL, PROJECT_URL_TEMPLATE
from tools.db import content_hash

__all__ = [
    "PEOPLE_SOURCE_URL",
    "MissingIdentifierError",
    "PayloadShapeError",
    "people_rows",
    "project_row",
]

# The people endpoint is one unpaged call, so every person row cites the same URL.
PEOPLE_SOURCE_URL: Final[str] = f"{PEOPLE_URL}?limit={DEFAULT_PEOPLE_LIMIT}"


class PayloadShapeError(ValueError):
    """Raised when a response body does not match the documented shape."""

    def __init__(self, context: str, expected: str) -> None:
        """Name what was being read and the JSON shape it should have been."""
        super().__init__(f"{context}: expected a JSON {expected}")


class MissingIdentifierError(ValueError):
    """Raised when a payload lacks its bronze primary key (NOT NULL in the DDL)."""

    def __init__(self, field: str, context: str) -> None:
        """Name the missing key and where it was expected."""
        super().__init__(f"{context}: missing or empty {field!r} (bronze primary key)")


def _as_object(value: Json, context: str) -> dict[str, Json]:
    """Narrow a JSON value to an object, failing loudly on shape drift."""
    if isinstance(value, dict):
        return value
    raise PayloadShapeError(context, "object")


def _as_array(value: Json, context: str) -> list[Json]:
    """Narrow a JSON value to an array, failing loudly on shape drift."""
    if isinstance(value, list):
        return value
    raise PayloadShapeError(context, "array")


def _verbatim(payload: dict[str, Json]) -> SinkValue:
    """View a JSON object as a VARIANT cell without copying."""
    # Json is a semantic subset of SinkValue; the cast bridges the container
    # invariance the type system cannot see through (tools.ddl_registry does
    # the same).
    return cast("SinkValue", payload)


def _contributions_by_user(data: dict[str, Json]) -> dict[str, Json]:
    """Read the contributions map, tolerating its absence."""
    value = data.get("contributionsByUserId")
    if value is None:
        return {}
    return _as_object(value, "people-v2 contributionsByUserId")


def people_rows(
    body: Json, *, scraped_at: datetime, ingested_at: datetime, run_id: str
) -> list[SinkRow]:
    """Split one bff-public-people-v2 body into bronze.hacknation_people_raw rows.

    Each person object is copied (never mutated) and joined with that user's
    contributions under a "contributions" key — an empty list when absent.

    Args:
        body: The full response body from HacknationClient.people().
        scraped_at: When the response was fetched.
        ingested_at: When this ingest run is writing.
        run_id: The scrape run identifier.

    Returns:
        One row per person, in response order.

    Raises:
        MissingIdentifierError: If a person entry has no usable user_id.
    """
    data = _as_object(_as_object(body, "people-v2 body").get("data"), "people-v2 data")
    contributions = _contributions_by_user(data)
    rows: list[SinkRow] = []
    for entry in _as_array(data.get("people"), "people-v2 people"):
        person = _as_object(entry, "people-v2 person entry")
        user_id = person.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise MissingIdentifierError("user_id", "people-v2 person entry")
        payload: dict[str, Json] = {**person, "contributions": contributions.get(user_id, [])}
        rows.append(
            {
                "user_id": user_id,
                "payload": _verbatim(payload),
                "content_hash": content_hash(payload),
                "source_url": PEOPLE_SOURCE_URL,
                "scraped_at": scraped_at,
                "ingested_at": ingested_at,
                "scrape_run_id": run_id,
            }
        )
    return rows


def project_row(body: Json, *, scraped_at: datetime, ingested_at: datetime, run_id: str) -> SinkRow:
    """Shape one bff-projects-public-v2 body into a bronze.hacknation_projects_raw row.

    Args:
        body: The full response body from HacknationClient.project().
        scraped_at: When the response was fetched.
        ingested_at: When this ingest run is writing.
        run_id: The scrape run identifier.

    Returns:
        One row keyed by the project id, with the "data" object stored verbatim.

    Raises:
        MissingIdentifierError: If the project data has no usable id.
    """
    data = _as_object(_as_object(body, "projects-v2 body").get("data"), "projects-v2 data")
    project_id = data.get("id")
    if not isinstance(project_id, str) or not project_id:
        raise MissingIdentifierError("id", "projects-v2 data")
    return {
        "project_id": project_id,
        "payload": _verbatim(data),
        "content_hash": content_hash(data),
        "source_url": PROJECT_URL_TEMPLATE.format(project_id=project_id),
        "scraped_at": scraped_at,
        "ingested_at": ingested_at,
        "scrape_run_id": run_id,
    }
