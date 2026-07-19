# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""One-shot load of the Papers-with-Code archive into bronze.paper_code_links.

The archive (Hugging Face `pwc-archive/links-between-paper-and-code`,
CC-BY-SA-4.0) is downloaded manually and loaded from a local file — its rows
are never committed to this repo; the checked-in test fixture is synthetic.
Rows without an arXiv id are dropped: they are not joinable (the acceptance
criterion is the join on arxiv_id) and NULL merge keys never match in MERGE,
so they would duplicate on every re-run.
"""

import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Final

import pyarrow.parquet as pq

from contracts.interfaces import Sink
from contracts.models import UpsertResult
from scrapers.common.jsonutil import as_list, as_mapping, get_str

PWC_TABLE: Final[str] = "bronze.paper_code_links"
PWC_KEYS: Final[tuple[str, ...]] = ("repo_url", "paper_arxiv_id")
PWC_DATASET_URL: Final[str] = (
    "https://huggingface.co/datasets/pwc-archive/links-between-paper-and-code"
)
CHUNK_ROWS: Final[int] = 50_000


class UnsupportedArchiveFormatError(ValueError):
    """The archive file extension is not one of .parquet/.json/.json.gz."""

    def __init__(self, path: Path) -> None:
        """Name the offending file in the message."""
        super().__init__(f"unsupported archive format: {path.name} (use .parquet/.json/.json.gz)")


def read_links(path: Path) -> list[dict[str, object]]:
    """Read the archive rows from a local file.

    Args:
        path: A .parquet, .json, or .json.gz file in the archive schema.

    Returns:
        The raw link rows.

    Raises:
        UnsupportedArchiveFormatError: For any other extension.
    """
    name = path.name.lower()
    if name.endswith(".parquet"):
        table = pq.read_table(path)  # pyright: ignore[reportUnknownMemberType] - pyarrow stubs are partial here
        return [as_mapping(row) for row in table.to_pylist()]
    if name.endswith(".json.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return [as_mapping(row) for row in as_list(json.load(handle))]
    if name.endswith(".json"):
        return [as_mapping(row) for row in as_list(json.loads(path.read_text(encoding="utf-8")))]
    raise UnsupportedArchiveFormatError(path)


def to_bronze_rows(
    items: list[dict[str, object]], ingested_at: datetime
) -> list[dict[str, object]]:
    """Map archive rows to bronze shape: drop NULL-key rows, dedupe in-file.

    Args:
        items: Raw archive rows.
        ingested_at: Ingestion timestamp for every row.

    Returns:
        Deduplicated bronze rows (last occurrence wins).
    """
    deduped: dict[tuple[str, str], dict[str, object]] = {}
    for item in items:
        arxiv_id = get_str(item, "paper_arxiv_id")
        repo_url = get_str(item, "repo_url")
        if not arxiv_id or not repo_url:
            continue
        deduped[(repo_url, arxiv_id)] = {
            "paper_arxiv_id": arxiv_id,
            "repo_url": repo_url,
            "is_official": bool(item.get("is_official")),
            "mentioned_in_paper": bool(item.get("mentioned_in_paper")),
            "source_url": PWC_DATASET_URL,
            "ingested_at": ingested_at,
        }
    return list(deduped.values())


def load_archive(path: Path, sink: Sink, ingested_at: datetime) -> list[UpsertResult]:
    """Load one archive file through the idempotent sink in 50k-row chunks.

    Args:
        path: The locally downloaded archive file.
        sink: The bronze sink (NullSink on --dry-run).
        ingested_at: Ingestion timestamp for every row.

    Returns:
        One UpsertResult per chunk.
    """
    rows = to_bronze_rows(read_links(path), ingested_at)
    results: list[UpsertResult] = []
    for start in range(0, len(rows), CHUNK_ROWS):
        chunk = rows[start : start + CHUNK_ROWS]
        results.append(sink.upsert(PWC_TABLE, chunk, list(PWC_KEYS)))
    return results
