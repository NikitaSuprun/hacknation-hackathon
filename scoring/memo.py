# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Memo generation: nine fixed sections, every bullet cited or marked missing.

The model answers through a structured-output schema; belt-and-braces beyond
the JSON Schema check, `assert_all_bullets_cited` re-verifies the citation
contract in code (a non-missing bullet cites at least one URL; a missing
bullet names the gap field that feeds the interview). Memos are append-only:
the new row is latest and prior latest rows are flipped.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from contracts.interfaces import LLMClient
from contracts.models import Json, SinkRow
from contracts.validation import load_schema, payload_errors
from scoring.snapshot import Row, get_bool
from scrapers.common.jsonutil import as_list, as_mapping, as_sink, get_str
from tools.db import canonical_json

MEMO_SECTION_NAMES: Final[tuple[str, ...]] = (
    "company_snapshot",
    "investment_hypotheses",
    "swot",
    "team_and_history",
    "problem_and_product",
    "technology_and_defensibility",
    "market_tam_sam_som",
    "competition",
    "traction_and_kpis",
)
MEMO_STATUS_DRAFT: Final[str] = "draft"


class MemoInvalidError(ValueError):
    """The generated memo violates the frozen memo schema."""

    def __init__(self, errors: list[str]) -> None:
        """Carry every violation in the message."""
        super().__init__("; ".join(errors) or "memo response was not a JSON object")


class UncitedBulletError(ValueError):
    """A non-missing bullet carries no evidence URL."""

    def __init__(self, section: str, text: str) -> None:
        """Name the offending section and bullet."""
        super().__init__(f"uncited bullet in {section}: {text[:80]!r}")


class MissingGapFieldError(ValueError):
    """A missing-marked bullet names no gap field for the interview."""

    def __init__(self, section: str, text: str) -> None:
        """Name the offending section and bullet."""
        super().__init__(f"missing bullet without gap_field in {section}: {text[:80]!r}")


def _bullet_urls(bullet: Mapping[str, Json]) -> list[str]:
    urls: list[str] = []
    for item in as_list(bullet.get("evidence")):
        url = get_str(as_mapping(item), "source_url")
        if url:
            urls.append(url)
    return urls


def assert_all_bullets_cited(sections: Mapping[str, Json]) -> None:
    """Verify the citation contract over every section bullet.

    Args:
        sections: The parsed memo sections payload.

    Raises:
        UncitedBulletError: If a non-missing bullet has no evidence URL.
        MissingGapFieldError: If a missing bullet names no gap field.
    """
    for section in MEMO_SECTION_NAMES:
        body = as_mapping(sections.get(section))
        for item in as_list(body.get("bullets")):
            bullet = as_mapping(item)
            text = get_str(bullet, "text") or ""
            missing = get_bool(bullet, "missing") is True
            if missing and not get_str(bullet, "gap_field"):
                raise MissingGapFieldError(section, text)
            if not missing and not _bullet_urls(bullet):
                raise UncitedBulletError(section, text)


@dataclass(frozen=True, slots=True)
class MemoRequest:
    """Everything one memo generation reads."""

    venture_id: str
    thesis_id: str | None
    run_id: str
    context: Mapping[str, Json]
    model_version: str
    prior_memos: tuple[Row, ...]


@dataclass(frozen=True, slots=True)
class MemoResult:
    """The new memo row plus prior-latest flips."""

    memo_row: SinkRow
    flipped_rows: tuple[SinkRow, ...]


def _flip_latest(prior_memos: tuple[Row, ...], venture_id: str) -> tuple[SinkRow, ...]:
    flipped: list[SinkRow] = []
    for row in prior_memos:
        if row.get("venture_id") != venture_id or get_bool(row, "is_latest") is not True:
            continue
        copy: SinkRow = {key: as_sink(value) for key, value in row.items()}
        copy["is_latest"] = False
        flipped.append(copy)
    return tuple(flipped)


def build_memo(
    request: MemoRequest,
    *,
    llm: LLMClient,
    clock: Callable[[], datetime],
    id_factory: Callable[[], str],
) -> MemoResult:
    """Generate one memo through the structured-output seam.

    Args:
        request: The pure inputs of the generation.
        llm: The LLM seam (Opus structured outputs in live runs).
        clock: Injected time source for generated_at.
        id_factory: Injected id source for memo_id.

    Returns:
        The memo row plus is_latest flips of prior memos.

    Raises:
        MemoInvalidError: If the response violates the memo schema.
    """
    prompt = (
        f"TASK:memo venture={request.venture_id}\n"
        "Write the nine-section investment memo. Every bullet must cite at "
        "least one source_url or be marked missing with the gap_field that "
        "feeds the interview.\n" + canonical_json(dict(request.context))
    )
    response = llm.complete(prompt, schema=load_schema("memo"))
    if response.parsed is None:
        raise MemoInvalidError([])
    sections: dict[str, Json] = dict(response.parsed)
    errors = payload_errors("memo", sections)
    if errors:
        raise MemoInvalidError(errors)
    assert_all_bullets_cited(sections)
    row: SinkRow = {
        "memo_id": id_factory(),
        "venture_id": request.venture_id,
        "thesis_id": request.thesis_id,
        "run_id": request.run_id,
        "sections": as_sink(sections),
        "model_version": request.model_version,
        "generated_at": clock(),
        "status": MEMO_STATUS_DRAFT,
        "is_latest": True,
    }
    return MemoResult(
        memo_row=row, flipped_rows=_flip_latest(request.prior_memos, request.venture_id)
    )
