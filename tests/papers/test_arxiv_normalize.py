# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""arXiv normalization: id splitting, record building, version semantics."""

from datetime import UTC, date, datetime
from typing import Final

import pytest

from scrapers.common.jsonutil import as_mapping
from scrapers.papers._atom import AtomEntry
from scrapers.papers.normalize import (
    MissingNativeIdError,
    arxiv_entry_to_record,
    arxiv_record_to_row,
    split_arxiv_id,
)

NOW: Final[datetime] = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
RUN_ID: Final[str] = "run-0001"


def entry(entry_id: str | None, version_title: str = "GraspFM") -> AtomEntry:
    return AtomEntry(
        entry_id=entry_id,
        title=version_title,
        summary="We present GraspFM. Code: github.com/grasplab/grasp-anything.",
        authors=("Léna Fischer", "Wei Zhang"),
        categories=("cs.RO", "cs.LG"),
        primary_category="cs.RO",
        comment="Project page: https://grasplab.ch",
        journal_ref=None,
        doi=None,
        published="2026-06-12T17:59:59Z",
        updated="2026-07-01T17:59:59Z",
        landing_url="http://arxiv.org/abs/2506.11111v2",
        pdf_url="http://arxiv.org/pdf/2506.11111v2",
    )


def test_split_arxiv_id_variants() -> None:
    assert split_arxiv_id("http://arxiv.org/abs/2506.11111v2") == ("2506.11111", 2)
    assert split_arxiv_id("2506.11111") == ("2506.11111", 1)
    assert split_arxiv_id("math/0211159v1") == ("math/0211159", 1)
    assert split_arxiv_id("http://arxiv.org/abs/math/0211159v3") == ("math/0211159", 3)


def test_entry_to_record_core_fields() -> None:
    record = arxiv_entry_to_record(entry("http://arxiv.org/abs/2506.11111v2"), NOW)
    assert record.data_source == "arxiv"
    assert record.source_native_id == "2506.11111"
    assert record.published_at == date(2026, 6, 12)
    assert [author.full_name for author in record.authors] == ["Léna Fischer", "Wei Zhang"]
    assert record.authors[0].position == 1
    assert record.code_links[0].url == "https://github.com/grasplab/grasp-anything"
    assert record.source_extras["version"] == 2
    assert record.publication_uid  # deterministic UUIDv5 minted via tools.ids


def test_missing_id_raises_for_reject_path() -> None:
    with pytest.raises(MissingNativeIdError):
        arxiv_entry_to_record(entry(None), NOW)


def test_row_matches_committed_fixture_shape() -> None:
    record = arxiv_entry_to_record(entry("http://arxiv.org/abs/2506.11111v2"), NOW)
    row = arxiv_record_to_row(record, RUN_ID, NOW, NOW)
    assert row["arxiv_id"] == "2506.11111"
    assert row["latest_version"] == 2
    assert row["source_url"] == "https://arxiv.org/abs/2506.11111"
    assert row["scrape_run_id"] == RUN_ID
    payload = as_mapping(row["payload"])
    # The committed fixture core keys, plus additive-only extensions.
    assert {"title", "abstract", "authors", "categories", "comment"} <= set(payload)
    assert payload["authors"] == ["Léna Fischer", "Wei Zhang"]
    assert payload["version"] == 2
    assert payload["code_links"] == ["https://github.com/grasplab/grasp-anything"]


def test_version_bump_changes_content_hash() -> None:
    row_v1 = arxiv_record_to_row(
        arxiv_entry_to_record(entry("http://arxiv.org/abs/2506.11111v1"), NOW), RUN_ID, NOW, NOW
    )
    row_v2 = arxiv_record_to_row(
        arxiv_entry_to_record(entry("http://arxiv.org/abs/2506.11111v2"), NOW), RUN_ID, NOW, NOW
    )
    assert row_v1["arxiv_id"] == row_v2["arxiv_id"]
    assert row_v1["content_hash"] != row_v2["content_hash"]
    assert row_v1["latest_version"] == 1
    assert row_v2["latest_version"] == 2


def test_identical_content_means_identical_hash() -> None:
    row_a = arxiv_record_to_row(
        arxiv_entry_to_record(entry("http://arxiv.org/abs/2506.11111v2"), NOW), RUN_ID, NOW, NOW
    )
    later = datetime(2026, 7, 20, 9, 0, 0, tzinfo=UTC)
    row_b = arxiv_record_to_row(
        arxiv_entry_to_record(entry("http://arxiv.org/abs/2506.11111v2"), later),
        "run-0002",
        later,
        later,
    )
    assert row_a["content_hash"] == row_b["content_hash"]
