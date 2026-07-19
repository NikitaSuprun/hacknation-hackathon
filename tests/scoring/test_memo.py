# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Memo: golden bytes, citation belt-and-braces, gap markers, latest flips."""

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
from tests.scoring.conftest import golden_text
from tools.llm import ScriptedLLMClient


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
