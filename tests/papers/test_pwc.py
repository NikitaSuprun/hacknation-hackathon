"""PwC archive load: format handling, NULL-key drops, in-file dedupe."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scrapers.papers.pwc_archive import (
    PWC_DATASET_URL,
    UnsupportedArchiveFormatError,
    load_archive,
    read_links,
    to_bronze_rows,
)
from tests.scrapers.conftest import RecordingSink

NOW: Final[datetime] = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
SAMPLE: Final[Path] = (
    Path(__file__).parents[2] / "scrapers" / "papers" / "fixtures" / "pwc_links_sample.json"
)


def test_synthetic_sample_drops_null_keys_and_dedupes() -> None:
    rows = to_bronze_rows(read_links(SAMPLE), NOW)
    assert len(rows) == 2
    by_key = {(str(row["repo_url"]), str(row["paper_arxiv_id"])): row for row in rows}
    winner = by_key[("https://github.com/grasplab/grasp-anything", "2506.11111")]
    # Last occurrence wins on in-file duplicates.
    assert winner["mentioned_in_paper"] is False
    assert winner["source_url"] == PWC_DATASET_URL
    assert winner["ingested_at"] == NOW


def test_parquet_and_json_read_identically(tmp_path: Path) -> None:
    items = json.loads(SAMPLE.read_text(encoding="utf-8"))
    parquet_path = tmp_path / "links.parquet"
    pq.write_table(pa.Table.from_pylist(items), parquet_path)  # pyright: ignore[reportUnknownMemberType] - pyarrow stubs are partial here
    assert to_bronze_rows(read_links(parquet_path), NOW) == to_bronze_rows(read_links(SAMPLE), NOW)


def test_unsupported_extension_raises() -> None:
    with pytest.raises(UnsupportedArchiveFormatError):
        read_links(Path("archive.csv"))


def test_load_archive_upserts_on_composite_key() -> None:
    sink = RecordingSink()
    results = load_archive(SAMPLE, sink, NOW)
    assert len(results) == 1
    table, rows, keys, _variants = sink.calls[0]
    assert table == "bronze.paper_code_links"
    assert keys == ["repo_url", "paper_arxiv_id"]
    assert len(rows) == 2
