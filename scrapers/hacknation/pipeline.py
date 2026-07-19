# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The full Hack Nation run: bronze sweep, CV enrichment, PSR merge, silver.

Unlike the other scrapers, Hack Nation loads silver directly (person source
records and projects) because the showcase is the only producer for those
rows. Stage order is load-bearing: CVs are fetched and parsed before the PSR
merge so their education keywords fold into identities, and the CV bronze rows
land last (people/projects fragments outrank CV fragments on merge).
"""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, cast

from databricks.sdk import WorkspaceClient
from structlog.typing import FilteringBoundLogger

from contracts.interfaces import Sink
from contracts.models import BronzeRecord, Json, PersonSourceRecord, SinkRow, SinkValue
from scrapers.common.base import RunnerDeps, execute_run
from scrapers.common.http import HttpClient
from scrapers.hacknation import cv, silver
from scrapers.hacknation.client import HacknationClient
from scrapers.hacknation.normalizer import (
    CVS_TABLE,
    PEOPLE_TABLE,
    PROJECTS_TABLE,
    HacknationNormalizer,
    merge_psrs,
    psr_fragment_from_cv,
)
from scrapers.hacknation.scraper import HacknationDeps, HacknationScraper
from tools.ddl_registry import table_schema

PSR_TABLE: Final[str] = "silver.person_source_record"
PROJECT_TABLE: Final[str] = "silver.project"


@dataclass(frozen=True, slots=True)
class PipelineDeps:
    """Everything one pipeline invocation composes over; tests inject fakes."""

    client: HacknationClient
    http: HttpClient
    runner: RunnerDeps
    since: date
    limit: int
    clock: Callable[[], datetime]
    run_id: str
    log: FilteringBoundLogger
    catalog: str
    fetch_cvs: bool
    workspace: WorkspaceClient | None


@dataclass(frozen=True, slots=True)
class PipelineSummary:
    """Row counts per stage, echoed by the CLI and pinned by the replay test."""

    people: int
    projects: int
    rejects: int
    cvs: int
    psr: int
    silver_projects: int


@dataclass(frozen=True, slots=True)
class _CvCapture:
    """One stored CV: its bronze row plus the education fragment (if any)."""

    row: SinkRow
    fragment: PersonSourceRecord | None


def run_pipeline(deps: PipelineDeps) -> PipelineSummary:
    """Run the bronze sweep and every post-bronze stage.

    Args:
        deps: The assembled pipeline dependencies.

    Returns:
        Row counts per stage.
    """
    scraper = HacknationScraper(
        HacknationDeps(
            client=deps.client,
            limit=deps.limit,
            clock=deps.clock,
            run_id=deps.run_id,
            log=deps.log,
        )
    )
    result = execute_run(scraper, deps.runner, deps.since)
    collected = scraper.collected
    captures = _cv_stage(deps, collected) if deps.fetch_cvs else []
    psr_count = _psr_stage(deps, collected, [c.fragment for c in captures if c.fragment])
    project_count = _project_stage(deps, collected)
    summary = PipelineSummary(
        people=sum(record.table == PEOPLE_TABLE for record in collected),
        projects=sum(record.table == PROJECTS_TABLE for record in collected),
        rejects=result.rejects,
        cvs=_upsert(deps.runner.sink, CVS_TABLE, [capture.row for capture in captures]),
        psr=psr_count,
        silver_projects=project_count,
    )
    _log_summary(deps.log, summary)
    return summary


def _log_summary(log: FilteringBoundLogger, summary: PipelineSummary) -> None:
    log.info(
        "pipeline complete",
        people=summary.people,
        projects=summary.projects,
        rejects=summary.rejects,
        cvs=summary.cvs,
        psr=summary.psr,
        silver_projects=summary.silver_projects,
    )


def _upsert(sink: Sink, table: str, rows: list[SinkRow]) -> int:
    """Registry-driven upsert: keys and VARIANT columns come from the DDL."""
    if not rows:
        return 0
    schema = table_schema(table)
    sink.upsert(table, rows, list(schema.primary_key), variant_cols=schema.variant_cols)
    return len(rows)


def _cv_stage(deps: PipelineDeps, collected: list[BronzeRecord]) -> list[_CvCapture]:
    """Fetch, parse, and (live only) store every referenced CV; upsert later."""
    targets = _cv_targets(collected)
    captures = [
        capture
        for user_id, cv_url in targets
        if (capture := _one_cv(deps, user_id, cv_url)) is not None
    ]
    deps.log.info("cv stage", targets=len(targets), stored=len(captures))
    return captures


def _cv_targets(collected: list[BronzeRecord]) -> list[tuple[str, str]]:
    """Unique (user_id, cv_url) pairs from project members, first sighting wins."""
    seen: dict[str, str] = {}
    for record in collected:
        for user_id, cv_url in _record_cv_refs(record):
            seen.setdefault(user_id, cv_url)
    return list(seen.items())


def _record_cv_refs(record: BronzeRecord) -> Iterator[tuple[str, str]]:
    if record.table != PROJECTS_TABLE:
        return
    payload = record.row.get("payload")
    if not isinstance(payload, dict):
        return
    for member in _members(payload):
        user_id = member.get("userId")
        cv_url = member.get("cvUrl")
        if isinstance(user_id, str) and user_id and isinstance(cv_url, str) and cv_url:
            yield user_id, cv_url


def _members(payload: Mapping[str, SinkValue]) -> list[Mapping[str, SinkValue]]:
    """Member payloads: authorProfile first, then team[] in order."""
    members: list[Mapping[str, SinkValue]] = []
    author = payload.get("authorProfile")
    if isinstance(author, dict):
        members.append(author)
    team = payload.get("team")
    if isinstance(team, list):
        members.extend(entry for entry in team if isinstance(entry, dict))
    return members


def _one_cv(deps: PipelineDeps, user_id: str, cv_url: str) -> _CvCapture | None:
    """Fetch and parse one CV; every failure degrades to None, never a crash."""
    pdf = cv.fetch_cv(cv_url, http=deps.http)
    if pdf is None:
        deps.log.warning("cv fetch failed", user_id=user_id, cv_url=cv_url)
        return None
    text = cv.extract_text(pdf)
    extraction = _extraction(deps, text)
    path = cv.volume_path(deps.catalog, user_id)
    if deps.workspace is not None:
        cv.upload_pdf(deps.workspace, path, pdf)
    now = deps.clock()
    row = cv.cv_row(
        cv.CvDocument(user_id=user_id, cv_url=cv_url, pdf_bytes=pdf),
        path,
        text,
        extraction,
        stamp=cv.IngestStamp(scraped_at=now, ingested_at=now, run_id=deps.run_id),
    )
    fragment = psr_fragment_from_cv(
        user_id, extraction.extracted, source_url=cv_url, scraped_at=now, ingested_at=now
    )
    return _CvCapture(row=row, fragment=fragment)


def _extraction(deps: PipelineDeps, text: str | None) -> cv.CvExtraction:
    """LLM extraction when a warehouse and text exist; 'offline' means none ran."""
    warehouse = deps.runner.warehouse
    if warehouse is None or text is None:
        return cv.CvExtraction(extracted=None, raw_response=None, model="offline")
    endpoint = cv.llm_endpoint()
    extracted, raw = cv.extract_facts(text, warehouse=warehouse, endpoint=endpoint)
    return cv.CvExtraction(extracted=extracted, raw_response=raw, model=endpoint)


def _psr_stage(
    deps: PipelineDeps,
    collected: list[BronzeRecord],
    cv_fragments: list[PersonSourceRecord],
) -> int:
    """Merge every sighting into one PSR per person and load silver."""
    normalizer = HacknationNormalizer()
    fragments: list[PersonSourceRecord] = []
    for record in collected:
        if record.table in (PEOPLE_TABLE, PROJECTS_TABLE):
            fragments.extend(normalizer.to_psr(record))
    # CV fragments merge last: scraped identity fields outrank parsed-PDF facts.
    fragments.extend(cv_fragments)
    rows = [record.to_row() for record in merge_psrs(fragments)]
    count = _upsert(deps.runner.sink, PSR_TABLE, rows)
    deps.log.info("psr stage", fragments=len(fragments), rows=count)
    return count


def _project_stage(deps: PipelineDeps, collected: list[BronzeRecord]) -> int:
    """Render every project payload as a silver.project row and load it."""
    now = deps.clock()
    rows = [
        row
        for record in collected
        if record.table == PROJECTS_TABLE and (row := _project_row(record, now)) is not None
    ]
    count = _upsert(deps.runner.sink, PROJECT_TABLE, rows)
    deps.log.info("silver project stage", rows=count)
    return count


def _project_row(record: BronzeRecord, now: datetime) -> SinkRow | None:
    source_url = record.row.get("source_url")
    scraped_at = record.row.get("scraped_at")
    if not isinstance(source_url, str) or not isinstance(scraped_at, datetime):
        return None  # impossible for rows our own builder shaped; keeps types honest
    return silver.project_row(
        _payload_json(record), source_url=source_url, scraped_at=scraped_at, updated_at=now
    )


def _payload_json(record: BronzeRecord) -> Json:
    """View a bronze VARIANT payload as Json again.

    The payload cell was cast Json -> SinkValue verbatim at row build time, so
    the reverse view is safe; the checkers cannot see through the invariant
    recursive aliases (same seam as bronze._verbatim).
    """
    return cast("Json", record.row.get("payload"))
