# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Memo: golden bytes, citation belt-and-braces, gap markers, latest flips."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Final

import pytest

from contracts.models import Json, LLMResponse
from fixtures import build
from fixtures.fake_embedding import fake_embedding
from scoring import scripted
from scoring.deps import ScoringDeps
from scoring.memo import (
    MemoInvalidError,
    MemoRequest,
    MissingGapFieldError,
    UncitedBulletError,
    assert_all_bullets_cited,
    build_memo,
)
from scoring.serialize import to_jsonl_lines
from scoring.snapshot import GoldInputs
from scrapers.common.jsonutil import as_list, as_mapping
from tests.scoring.conftest import golden_text
from tools.llm import ScriptedLLMClient

REPAIR_NOW: Final[datetime] = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)


def fixture_request(prior: tuple[dict[str, Json], ...] = ()) -> MemoRequest:
    return MemoRequest(
        venture_id=build.GRASP_VENTURE,
        thesis_id=build.THESIS_ID,
        run_id=build.RUN_ID,
        context={"name": "GraspLab"},
        model_version=scripted.MEMO_MODEL_VERSION,
        prior_memos=prior,
    )


def test_memo_row_byte_reproduces_golden_file(deps: ScoringDeps) -> None:
    result = build_memo(
        fixture_request(), llm=deps.llm, clock=deps.clock, id_factory=lambda: build.MEMO_ID
    )
    assert to_jsonl_lines([result.memo_row]) == golden_text("gold.memo")


def test_uncited_bullet_raises() -> None:
    sections = scripted.fixture_memo_sections()
    sections["swot"] = {"bullets": [{"text": "Unsubstantiated strength claim."}]}
    with pytest.raises(UncitedBulletError, match="swot"):
        assert_all_bullets_cited(sections)


def test_missing_bullet_without_gap_field_raises() -> None:
    sections = scripted.fixture_memo_sections()
    sections["market_tam_sam_som"] = {
        "bullets": [{"text": "Sizing unknown.", "missing": True}],
        "tam": None,
        "sam": None,
        "som": None,
        "assumptions": [],
    }
    with pytest.raises(MissingGapFieldError, match="market_tam_sam_som"):
        assert_all_bullets_cited(sections)


def test_fixture_missing_bullets_carry_gap_fields() -> None:
    sections = scripted.fixture_memo_sections()
    traction = sections["traction_and_kpis"]
    assert isinstance(traction, dict)
    bullets = traction["bullets"]
    assert isinstance(bullets, list)
    missing = [b for b in bullets if isinstance(b, dict) and b.get("missing") is True]
    assert missing
    assert all(b.get("gap_field") for b in missing)
    assert_all_bullets_cited(sections)  # the golden sections pass the check


def test_schema_violation_raises_memo_invalid(deps: ScoringDeps) -> None:
    broken = LLMResponse(text="{}", parsed={"schema_version": 1}, model="scripted")
    llm = ScriptedLLMClient(
        {f"TASK:memo venture={build.GRASP_VENTURE}": broken}, embedder=fake_embedding
    )
    with pytest.raises(MemoInvalidError, match="required"):
        build_memo(fixture_request(), llm=llm, clock=deps.clock, id_factory=lambda: build.MEMO_ID)


def test_prior_latest_memos_are_flipped(deps: ScoringDeps, gold: GoldInputs) -> None:
    prior = tuple(dict(row) for row in gold.memos)
    result = build_memo(
        fixture_request(prior), llm=deps.llm, clock=deps.clock, id_factory=lambda: build.MEMO_ID
    )
    assert len(result.flipped_rows) == 1
    assert result.flipped_rows[0]["is_latest"] is False
    assert result.memo_row["is_latest"] is True


class _TwoShotLLM:
    """Answers badly once, then correctly — the repair path under test."""

    def __init__(self, bad: Json, good: Json) -> None:
        """Queue the invalid then the valid response."""
        self.prompts: Final[list[str]] = []
        self._queue: Final[list[Json]] = [bad, good]

    def complete(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Json] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Pop the next canned response."""
        del schema, model
        self.prompts.append(prompt)
        payload = self._queue.pop(0)
        return LLMResponse(text="", parsed=as_mapping(payload), model="test")

    def embed(self, text: str) -> list[float]:
        """Unused by the memo job."""
        del text
        return []


def _strip_bullet_text(sections: Json) -> dict[str, Json]:
    stripped = as_mapping(sections)
    body = as_mapping(stripped["company_snapshot"])
    bullets = [
        {key: value for key, value in as_mapping(bullet).items() if key != "text"}
        for bullet in as_list(body["bullets"])
    ]
    patched: dict[str, Json] = dict(stripped)
    section: dict[str, Json] = dict(body)
    section["bullets"] = [as_mapping(bullet) for bullet in bullets]
    patched["company_snapshot"] = section
    return patched


def test_schema_violation_is_repaired_with_the_errors_fed_back() -> None:
    good = scripted.fixture_memo_sections()
    llm = _TwoShotLLM(_strip_bullet_text(good), good)
    result = build_memo(
        MemoRequest(
            venture_id=build.GRASP_VENTURE,
            thesis_id=build.THESIS_ID,
            run_id="run-repair",
            context={"name": "GraspLab"},
            model_version="test",
            prior_memos=(),
        ),
        llm=llm,
        clock=lambda: REPAIR_NOW,
        id_factory=lambda: "memo-repair",
    )
    assert result.memo_row["memo_id"] == "memo-repair"
    assert len(llm.prompts) == 2
    assert "violated the schema" in llm.prompts[1]
    assert "'text' is a required property" in llm.prompts[1]
