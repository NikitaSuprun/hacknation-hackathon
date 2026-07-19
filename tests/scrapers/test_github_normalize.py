# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Normalization: golden bronze rows, hash recomputation, the rejects path."""

from datetime import UTC, datetime
from typing import Final

from contracts.models import RawBatch
from scrapers.github.normalize import normalize_batch
from tools.db import content_hash

SCRAPED_AT: Final[datetime] = datetime(2026, 7, 19, 10, 0, 0, tzinfo=UTC)
NOW: Final[datetime] = datetime(2026, 7, 19, 10, 5, 0, tzinfo=UTC)
RUN_ID: Final[str] = "run-0001"
SHA: Final[str] = "a" * 40


def batch(*items: dict[str, object]) -> RawBatch:
    return RawBatch(source="github", items=tuple(items))


def test_repo_item_becomes_golden_bronze_row() -> None:
    payload: dict[str, object] = {"nameWithOwner": "o/r", "funded_signals": ["a16z"]}
    item: dict[str, object] = {
        "kind": "repo",
        "repo_id": 9001,
        "full_name": "o/r",
        "payload": payload,
        "etag": 'W/"x"',
        "source_url": "https://github.com/o/r",
        "scraped_at": SCRAPED_AT,
    }
    (record,) = normalize_batch(batch(item), RUN_ID, NOW)
    assert record.table == "bronze.github_repos_raw"
    assert record.row == {
        "repo_id": 9001,
        "full_name": "o/r",
        "payload": payload,
        "content_hash": content_hash(payload),
        "etag": 'W/"x"',
        "source_url": "https://github.com/o/r",
        "scraped_at": SCRAPED_AT,
        "ingested_at": NOW,
        "scrape_run_id": RUN_ID,
    }
    assert (
        record.row["content_hash"]
        == "12c8b10ba372fba34770893caf71ac4908cd40318039188166663afed537491a"
    )


def test_commit_row_has_no_content_hash() -> None:
    item: dict[str, object] = {
        "kind": "commit",
        "repo_id": 9001,
        "sha": SHA,
        "author_user_id": None,
        "payload": {"oid": SHA},
        "source_url": f"https://github.com/o/r/commit/{SHA}",
        "scraped_at": SCRAPED_AT,
    }
    (record,) = normalize_batch(batch(item), RUN_ID, NOW)
    assert record.table == "bronze.github_commits_raw"
    assert "content_hash" not in record.row
    assert record.row["author_user_id"] is None


def test_invalid_user_diverts_to_rejects_with_login_key() -> None:
    item: dict[str, object] = {
        "kind": "user",
        "user_id": None,
        "login": "broken-profile",
        "payload": {},
        "source_url": "https://github.com/broken-profile",
        "scraped_at": SCRAPED_AT,
    }
    (record,) = normalize_batch(batch(item), RUN_ID, NOW)
    assert record.table == "bronze._rejects"
    assert record.row["source"] == "github"
    assert record.row["natural_key"] == "broken-profile"
    assert record.row["scrape_run_id"] == RUN_ID
    assert record.row["ingested_at"] == NOW
    error = record.row["error"]
    assert isinstance(error, str)
    assert "user_id" in error


def test_error_kind_item_maps_straight_to_rejects() -> None:
    item: dict[str, object] = {
        "kind": "error",
        "natural_key": "octo/gone",
        "error": "still boom",
        "raw": {"key": "octo/gone"},
    }
    (record,) = normalize_batch(batch(item), RUN_ID, NOW)
    assert record.table == "bronze._rejects"
    assert record.row["natural_key"] == "octo/gone"
    assert record.row["error"] == "still boom"


def test_malformed_sha_rejected() -> None:
    item: dict[str, object] = {
        "kind": "commit",
        "repo_id": 9001,
        "sha": "not-a-sha",
        "author_user_id": 1,
        "payload": {},
        "source_url": "https://github.com/o/r/commit/x",
        "scraped_at": SCRAPED_AT,
    }
    (record,) = normalize_batch(batch(item), RUN_ID, NOW)
    assert record.table == "bronze._rejects"
    assert record.row["natural_key"] == "not-a-sha"
