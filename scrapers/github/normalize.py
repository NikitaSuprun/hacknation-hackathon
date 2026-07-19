# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Raw items to bronze rows; validation failures divert to bronze._rejects.

Payload composition (done fetch-side, documented here): a repo payload is the
GraphQL repository object plus `readme_md` (truncated) and `funded_signals`;
a user payload is the GraphQL profile plus derived `candidate_emails` (commit
author emails with sha provenance, noreply excluded); commit payloads keep the
GraphQL history node verbatim so bronze stays recomputable.
"""

from datetime import datetime
from typing import Final

from pydantic import ValidationError

from contracts.models import BronzeRecord, Json, RawBatch
from scrapers.common.jsonutil import as_sink
from scrapers.common.models import RejectRow
from scrapers.github.models import RAW_ITEM_ADAPTER, CommitRaw, RepoRaw, UserRaw
from tools.db import canonical_json, content_hash

SOURCE: Final[str] = "github"
ERROR_KIND: Final[str] = "error"
REPOS_TABLE: Final[str] = "bronze.github_repos_raw"
USERS_TABLE: Final[str] = "bronze.github_users_raw"
COMMITS_TABLE: Final[str] = "bronze.github_commits_raw"


def _natural_key(item: dict[str, Json]) -> str:
    for key in ("full_name", "login", "sha", "natural_key"):
        value = item.get(key)
        if isinstance(value, str):
            return value
    return "unknown"


def _jsonable(value: object) -> object:
    return value.isoformat() if isinstance(value, datetime) else value


def _reject(item: dict[str, Json], error: str, run_id: str, now: datetime) -> BronzeRecord:
    return RejectRow(
        source=SOURCE,
        natural_key=_natural_key(item),
        error=error,
        raw=canonical_json({k: _jsonable(v) for k, v in item.items() if k != "payload"}),
        scrape_run_id=run_id,
        ingested_at=now,
    ).to_bronze()


def _repo_row(model: RepoRaw, run_id: str, now: datetime) -> BronzeRecord:
    return BronzeRecord(
        table=REPOS_TABLE,
        row={
            "repo_id": model.repo_id,
            "full_name": model.full_name,
            "payload": as_sink(model.payload),
            "content_hash": content_hash(model.payload),
            "etag": model.etag,
            "source_url": model.source_url,
            "scraped_at": model.scraped_at,
            "ingested_at": now,
            "scrape_run_id": run_id,
        },
    )


def _user_row(model: UserRaw, run_id: str, now: datetime) -> BronzeRecord:
    return BronzeRecord(
        table=USERS_TABLE,
        row={
            "user_id": model.user_id,
            "login": model.login,
            "payload": as_sink(model.payload),
            "content_hash": content_hash(model.payload),
            "source_url": model.source_url,
            "scraped_at": model.scraped_at,
            "ingested_at": now,
            "scrape_run_id": run_id,
        },
    )


def _commit_row(model: CommitRaw, run_id: str, now: datetime) -> BronzeRecord:
    # bronze.github_commits_raw has no content_hash column: commits are
    # immutable by sha, so the sink falls back to whole-row comparison.
    return BronzeRecord(
        table=COMMITS_TABLE,
        row={
            "repo_id": model.repo_id,
            "sha": model.sha,
            "author_user_id": model.author_user_id,
            "payload": as_sink(model.payload),
            "source_url": model.source_url,
            "scraped_at": model.scraped_at,
            "ingested_at": now,
            "scrape_run_id": run_id,
        },
    )


def _one(item: dict[str, Json], run_id: str, now: datetime) -> BronzeRecord:
    if item.get("kind") == ERROR_KIND:
        return _reject(item, str(item.get("error", "fetch error")), run_id, now)
    try:
        model = RAW_ITEM_ADAPTER.validate_python(item)
    except ValidationError as exc:
        return _reject(item, str(exc), run_id, now)
    if isinstance(model, RepoRaw):
        return _repo_row(model, run_id, now)
    if isinstance(model, UserRaw):
        return _user_row(model, run_id, now)
    return _commit_row(model, run_id, now)


def normalize_batch(raw: RawBatch, run_id: str, now: datetime) -> list[BronzeRecord]:
    """Validate one raw batch into bronze records (rejects included, no raises).

    Args:
        raw: The fetched batch of kind-tagged items.
        run_id: This run's scrape_run_id.
        now: Ingestion timestamp for every produced row.

    Returns:
        Bronze records for the sink, one per item.
    """
    return [_one(dict(item), run_id, now) for item in raw.items]
