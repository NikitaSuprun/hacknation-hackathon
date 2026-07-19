# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""People + project details into the two Hack Nation bronze tables.

One people request supplies the identity spine; contributionsByUserId yields
the unique project ids fetched one by one (gently rate limited). Rows MERGE
through the shared sink with registry keys, so re-runs are idempotent and the
content_hash skip plus the hacknation suppression guard apply automatically.
A project detail that answers non-JSON (SPA fallback) or keeps failing
upstream (the endpoint 502s on some ids) is skipped and counted, never
fatal — one bad project must not lose a whole run's work.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from structlog.typing import FilteringBoundLogger

from contracts.interfaces import Sink
from contracts.models import Json, SinkRow
from er.io import sink_all
from scrapers.common.http import HttpStatusError
from scrapers.common.jsonutil import as_list, as_mapping, as_sink, get_list, get_map
from sources.hacknation.client import (
    DEFAULT_PEOPLE_LIMIT,
    PEOPLE_URL,
    PROJECT_URL,
    HacknationClient,
    NotJsonResponseError,
)
from tools.db import content_hash

PEOPLE_TABLE: Final[str] = "bronze.hacknation_people_raw"
PROJECTS_TABLE: Final[str] = "bronze.hacknation_projects_raw"


@dataclass(frozen=True, slots=True)
class IngestContext:
    """Everything one ingest run needs, injected for testability."""

    client: HacknationClient
    sink: Sink
    log: FilteringBoundLogger
    clock: Callable[[], datetime]
    run_id: str
    limit: int


@dataclass(frozen=True, slots=True)
class IngestReport:
    """Outcome summary of one ingest run."""

    people: int
    projects: int
    skipped_non_json: int
    skipped_failed: int


def _key_str(value: Json) -> str | None:
    """A string key from a string-or-int JSON id."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str | int):
        return str(value)
    return None


def _people_row(person: dict[str, Json], now: datetime, run_id: str) -> SinkRow | None:
    user_id = _key_str(person.get("user_id"))
    if user_id is None:
        return None
    return {
        "user_id": user_id,
        "payload": as_sink(person),
        "content_hash": content_hash(person),
        "source_url": f"{PEOPLE_URL}?limit={DEFAULT_PEOPLE_LIMIT}",
        "scraped_at": now,
        "ingested_at": now,
        "scrape_run_id": run_id,
    }


def _project_row(project_id: str, detail: dict[str, Json], now: datetime, run_id: str) -> SinkRow:
    return {
        "project_id": project_id,
        "payload": as_sink(detail),
        "content_hash": content_hash(detail),
        "source_url": f"{PROJECT_URL}?id={project_id}",
        "scraped_at": now,
        "ingested_at": now,
        "scrape_run_id": run_id,
    }


def project_ids(data: dict[str, Json]) -> list[str]:
    """Unique project ids named in contributionsByUserId, sorted.

    Args:
        data: The people endpoint's `data` object.

    Returns:
        The sorted unique ids.
    """
    ids: set[str] = set()
    for contributions in get_map(data, "contributionsByUserId").values():
        for entry in as_list(contributions):
            project_id = _key_str(as_mapping(entry).get("id"))
            if project_id is not None:
                ids.add(project_id)
    return sorted(ids)


@dataclass(frozen=True, slots=True)
class _ProjectFetch:
    """Rows plus the two per-project skip tallies."""

    rows: list[SinkRow]
    skipped_non_json: int
    skipped_failed: int


def _fetch_projects(context: IngestContext, ids: list[str], now: datetime) -> _ProjectFetch:
    rows: list[SinkRow] = []
    skipped_non_json = 0
    skipped_failed = 0
    for project_id in ids:
        try:
            detail = context.client.project(project_id)
        except NotJsonResponseError:
            context.log.warning("spa fallback, skipping project", project_id=project_id)
            skipped_non_json += 1
            continue
        except HttpStatusError as error:
            # The upstream function 502s on some project ids even after the
            # client's retries; one bad project must not abort the run.
            context.log.warning(
                "project fetch failed, skipping", project_id=project_id, status=error.status
            )
            skipped_failed += 1
            continue
        rows.append(_project_row(project_id, detail, now, context.run_id))
    return _ProjectFetch(
        rows=rows, skipped_non_json=skipped_non_json, skipped_failed=skipped_failed
    )


def run_ingest(context: IngestContext) -> IngestReport:
    """Fetch people plus every referenced project and MERGE them into bronze.

    Args:
        context: The injected run dependencies.

    Returns:
        The run summary.
    """
    now = context.clock()
    data = context.client.people()
    people_rows = [
        row
        for person in get_list(data, "people")
        if isinstance(person, dict)
        and (row := _people_row(as_mapping(person), now, context.run_id)) is not None
    ]
    ids = project_ids(data)
    if context.limit > 0:
        ids = ids[: context.limit]
    fetched = _fetch_projects(context, ids, now)
    results = sink_all(context.sink, {PEOPLE_TABLE: people_rows, PROJECTS_TABLE: fetched.rows})
    for table, result in results.items():
        context.log.info(
            "upserted",
            table=table,
            inserted=result.inserted,
            updated=result.updated,
            skipped_unchanged=result.skipped_unchanged,
            suppressed=result.suppressed,
        )
    return IngestReport(
        people=len(people_rows),
        projects=len(fetched.rows),
        skipped_non_json=fetched.skipped_non_json,
        skipped_failed=fetched.skipped_failed,
    )
