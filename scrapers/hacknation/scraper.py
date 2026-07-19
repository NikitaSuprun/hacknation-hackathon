# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The Hack Nation scraper: one people sweep, then every referenced project.

Each people entry becomes its own raw item so a single malformed profile
rejects alone instead of sinking the whole directory. The scraper keeps every
bronze record it emits (`collected`) because the post-run PSR/silver/CV stages
derive from the same payloads — a warehouse readback would break the
credential-free `--fixtures --dry-run` path.
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from structlog.typing import FilteringBoundLogger

from contracts.models import BronzeRecord, Cursor, Json, RawBatch, SinkRow
from scrapers.common.jsonutil import as_list, as_mapping, get_list, get_map, get_str
from scrapers.common.models import RejectRow
from scrapers.hacknation.bronze import (
    MissingIdentifierError,
    PayloadShapeError,
    people_rows,
    project_row,
)
from scrapers.hacknation.client import HacknationClient, NonJsonResponseError
from scrapers.hacknation.normalizer import PEOPLE_TABLE, PROJECTS_TABLE, SOURCE
from tools.db import canonical_json

PERSON_KIND: Final[str] = "person"
PROJECT_KIND: Final[str] = "project"
ERROR_KIND: Final[str] = "error"


@dataclass(frozen=True, slots=True)
class HacknationDeps:
    """Everything the scraper composes over; injected for deterministic tests."""

    client: HacknationClient
    limit: int
    clock: Callable[[], datetime]
    run_id: str
    log: FilteringBoundLogger


class HacknationScraper:
    """RunnableScraper implementation for the Hack Nation showcase."""

    source: str = SOURCE

    def __init__(self, deps: HacknationDeps) -> None:
        """Start with an empty per-run record cache."""
        self._deps: Final[HacknationDeps] = deps
        self.collected: Final[list[BronzeRecord]] = []

    def fetch(self, cursor: Cursor) -> Iterator[RawBatch]:
        """Sweep the people directory, then fetch each referenced project once.

        Args:
            cursor: Unused (the showcase is small; every run is a full sweep).

        Yields:
            One batch of per-person items, then one batch per unique project.
        """
        del cursor
        data = get_map(as_mapping(self._deps.client.people()), "data")
        people = get_list(data, "people")
        contributions = get_map(data, "contributionsByUserId")
        if not people:
            self._deps.log.warning("people list empty or unexpectedly shaped")
        yield RawBatch(
            source=SOURCE,
            items=tuple(_person_item(person, contributions) for person in people),
        )
        for project_id in self._project_ids(contributions):
            yield self._project_batch(project_id)

    def normalize(self, raw: RawBatch) -> list[BronzeRecord]:
        """Validate raw items into bronze rows; malformed items become rejects.

        Args:
            raw: One fetched batch.

        Returns:
            Bronze records (rejects included), also cached in `collected`.
        """
        now = self._deps.clock()
        records = [self._one(dict(item), now) for item in raw.items]
        self.collected.extend(records)
        return records

    def next_cursor(self) -> Cursor:
        """Record the run time (full sweeps need no incremental position).

        Returns:
            The cursor for ops.scrape_state.
        """
        return Cursor(source=SOURCE, state={"last_run_at": self._deps.clock().isoformat()})

    def _project_ids(self, contributions: dict[str, Json]) -> list[str]:
        """Unique project ids in first-sighting order, capped by the limit."""
        seen: dict[str, None] = {}
        for entries in contributions.values():
            for entry in as_list(entries):
                project_id = get_str(as_mapping(entry), "id")
                if project_id:
                    seen.setdefault(project_id, None)
        ids = list(seen)
        return ids[: self._deps.limit] if self._deps.limit > 0 else ids

    def _project_batch(self, project_id: str) -> RawBatch:
        """One project fetch; a non-JSON answer rejects instead of crashing."""
        try:
            body = self._deps.client.project(project_id)
        except (NonJsonResponseError, json.JSONDecodeError) as exc:
            item: dict[str, Json] = {
                "kind": ERROR_KIND,
                "natural_key": project_id,
                "error": str(exc),
            }
            return RawBatch(source=SOURCE, items=(item,))
        return RawBatch(
            source=SOURCE,
            items=({"kind": PROJECT_KIND, "project_id": project_id, "body": body},),
        )

    def _one(self, item: dict[str, Json], now: datetime) -> BronzeRecord:
        """Route one raw item to its bronze table, or to bronze._rejects."""
        try:
            record = self._routed(item, now)
        except (PayloadShapeError, MissingIdentifierError) as exc:
            return self._reject(item, str(exc), now)
        if record is not None:
            return record
        error = get_str(item, "error") or f"unroutable raw item kind {item.get('kind')!r}"
        return self._reject(item, error, now)

    def _routed(self, item: dict[str, Json], now: datetime) -> BronzeRecord | None:
        """The bronze record for a person/project item; None for error items."""
        kind = item.get("kind")
        if kind == PERSON_KIND:
            return BronzeRecord(table=PEOPLE_TABLE, row=self._person_row(item, now))
        if kind == PROJECT_KIND:
            row = project_row(
                item.get("body"), scraped_at=now, ingested_at=now, run_id=self._deps.run_id
            )
            return BronzeRecord(table=PROJECTS_TABLE, row=row)
        return None

    def _person_row(self, item: dict[str, Json], now: datetime) -> SinkRow:
        """Rebuild the one-person body so the whole-response row builder applies."""
        person = item.get("person")
        by_user: dict[str, Json] = {}
        user_id = get_str(as_mapping(person), "user_id")
        if user_id:
            by_user[user_id] = item.get("contributions", [])
        body: dict[str, Json] = {"data": {"people": [person], "contributionsByUserId": by_user}}
        return people_rows(body, scraped_at=now, ingested_at=now, run_id=self._deps.run_id)[0]

    def _reject(self, item: dict[str, Json], error: str, now: datetime) -> BronzeRecord:
        key = _natural_key(item)
        return RejectRow(
            source=SOURCE,
            natural_key=key,
            error=error,
            raw=canonical_json({"kind": item.get("kind"), "natural_key": key}),
            scrape_run_id=self._deps.run_id,
            ingested_at=now,
        ).to_bronze()


def _person_item(person: Json, contributions: dict[str, Json]) -> dict[str, Json]:
    """One raw item per person, carrying that user's contributions along."""
    user_id = get_str(as_mapping(person), "user_id")
    return {
        "kind": PERSON_KIND,
        "person": person,
        "contributions": contributions.get(user_id, []) if user_id else [],
    }


def _natural_key(item: dict[str, Json]) -> str:
    """The reject key: the project id, the user id, or a named placeholder."""
    if item.get("kind") == PERSON_KIND:
        return get_str(as_mapping(item.get("person")), "user_id") or "missing-user-id"
    return get_str(item, "project_id") or get_str(item, "natural_key") or "missing-project-id"
