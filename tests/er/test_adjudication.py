# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""T9: LLM adjudication - verdicts, persistence, skips, and schema failures."""

import json
from datetime import datetime

import pytest

from contracts.models import LLMResponse
from er.adjudicate import (
    VERDICT_SCHEMA,
    VerdictSchemaError,
    adjudicate_pairs,
    pair_id,
    settled_pair_ids,
)
from er.models import PsrView, ScoredPair, psr_view
from er.offline import OFFLINE_MODEL, frozen_clock, scripted_responses
from er.pipeline import ErInputs, ErOutputs
from fixtures import build as fx
from fixtures.fake_embedding import fake_embedding
from tests.er.conftest import fixture_lines
from tests.er.conftest import render as render_row
from tools.llm import ScriptedLLMClient


def _views(inputs: ErInputs) -> dict[str, PsrView]:
    return {str(row["source_record_id"]): psr_view(row) for row in inputs.psr_rows}


def _wei_pair() -> ScoredPair:
    left, right = sorted((fx.PSR_WEI_A_GITHUB, fx.PSR_WEI_A_OPENALEX))
    return ScoredPair(left=left, right=right, probability=0.87, comparison={})


def _llm(inputs: ErInputs) -> ScriptedLLMClient:
    return ScriptedLLMClient(scripted_responses(inputs), embedder=fake_embedding)


def test_match_verdict_produces_row_and_evidence(inputs: ErInputs) -> None:
    verdicts = adjudicate_pairs(
        [_wei_pair()],
        _views(inputs),
        _llm(inputs),
        existing_pair_ids=frozenset(),
        clock=frozen_clock,
        pipeline_version=fx.PIPELINE_VERSION,
    )
    (verdict,) = verdicts
    assert verdict.verdict == "match"
    assert verdict.row["pair_id"] == pair_id(fx.PSR_WEI_A_GITHUB, fx.PSR_WEI_A_OPENALEX)
    assert verdict.row["model"] == OFFLINE_MODEL
    assert verdict.row["adjudicated_at"] == datetime.fromisoformat(fx.T_UPDATED)
    assert verdict.evidence == {
        "verdict": "match",
        "rationale": "Same org, same robotics focus, login matches name",
        "fields_supporting": ["org_norm", "keywords", "country_code"],
    }


def test_match_link_reproduces_wei_fixture_bytes(scratch_outputs: ErOutputs) -> None:
    expected = next(
        line
        for line in fixture_lines("silver.person_source_link")
        if json.loads(line)["source_record_id"] == fx.PSR_WEI_A_GITHUB
        and json.loads(line)["match_method"] == "llm_adjudication"
    )
    produced = next(
        row
        for row in scratch_outputs.tables["silver.person_source_link"]
        if str(row["source_record_id"]) == fx.PSR_WEI_A_GITHUB
    )
    assert render_row(produced) == expected


def test_settled_pairs_are_skipped(inputs: ErInputs) -> None:
    settled = frozenset({pair_id(fx.PSR_WEI_A_GITHUB, fx.PSR_WEI_A_OPENALEX)})
    verdicts = adjudicate_pairs(
        [_wei_pair()],
        _views(inputs),
        _llm(inputs),
        existing_pair_ids=settled,
        clock=frozen_clock,
        pipeline_version=fx.PIPELINE_VERSION,
    )
    assert verdicts == []
    assert settled_pair_ids([{"pair_id": "abc"}]) == frozenset({"abc"})


def test_schema_invalid_response_raises_typed_error(inputs: ErInputs) -> None:
    broken = ScriptedLLMClient(
        {},
        embedder=fake_embedding,
        default=LLMResponse(text="not json at all", parsed=None, model="broken"),
    )
    with pytest.raises(VerdictSchemaError):
        adjudicate_pairs(
            [_wei_pair()],
            _views(inputs),
            broken,
            existing_pair_ids=frozenset(),
            clock=frozen_clock,
            pipeline_version=fx.PIPELINE_VERSION,
        )


def test_verdict_schema_shape() -> None:
    assert VERDICT_SCHEMA["required"] == ["verdict", "rationale", "fields_supporting"]
    properties = VERDICT_SCHEMA["properties"]
    assert isinstance(properties, dict)
    assert set(properties) == {"verdict", "rationale", "fields_supporting"}
