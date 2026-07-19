# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Ranking contract: pool join, the nine score columns, VARIANT-as-string,
and the client re-rank mirror."""

import json
from typing import Final

import pytest

from app.rescoring import client_final_score
from contracts.models import Json
from fixtures import build
from scoring.snapshot import get_float
from scrapers.common.jsonutil import as_mapping, get_str
from tests.app.conftest import AppClient

S_COLUMNS: Final[tuple[str, ...]] = (
    "s_individual_experience",
    "s_schools",
    "s_network_ties",
    "s_prior_collaboration",
    "s_problem_realness",
    "s_product_defensibility",
    "s_market",
    "s_traction",
    "ideal_match",
)
CATEGORY_NAMES: Final[tuple[str, ...]] = (
    "individual_experience",
    "schools",
    "network_ties",
    "prior_collaboration",
    "problem_realness",
    "product_defensibility",
    "market",
    "traction",
    "ideal_match",
)


def _ranking(client: AppClient, auth: dict[str, str]) -> dict[str, Json]:
    response = client.get("/v1/ranking", headers=auth)
    assert response.status_code == 200
    return response.body


def _weighted_sum(weights: dict[str, Json], row: dict[str, Json], names: tuple[str, ...]) -> float:
    total = 0.0
    for name in names:
        column = "ideal_match" if name == "ideal_match" else f"s_{name}"
        total += (get_float(weights, f"w_{name}") or 0.0) * (get_float(row, column) or 0.0)
    return total


def test_ranking_returns_the_fixture_venture_with_all_score_columns(
    client: AppClient, auth: dict[str, str]
) -> None:
    response = client.get("/v1/ranking", headers=auth)
    assert response.status_code == 200
    assert response.body["thesis_id"] == build.THESIS_ID
    ventures = response.items("ventures")
    # GraspLab (78.4) ranks above the WS-G VoiceLab hackathon venture (54.9).
    ranked_ids = [get_str(row, "venture_id") for row in ventures]
    assert ranked_ids[0] == build.GRASP_VENTURE
    assert len(ranked_ids) == 2
    row = ventures[0]
    body = response.body
    assert row["final_score"] == 78.4
    assert row["confidence"] == 0.82
    for column in S_COLUMNS:
        assert isinstance(row[column], float), column
    weights = as_mapping(body.get("weights"))
    assert weights["w_ideal_match"] == 0.1


def test_breakdown_travels_as_a_json_string(client: AppClient, auth: dict[str, str]) -> None:
    response = client.get("/v1/ranking", headers=auth)
    row = response.items("ventures")[0]
    breakdown_text = row["breakdown"]
    assert isinstance(breakdown_text, str)
    breakdown = as_mapping(json.loads(breakdown_text))
    assert breakdown["schema_version"] == 1
    assert set(as_mapping(breakdown.get("categories"))) >= {"schools", "traction", "ideal_match"}


def test_client_rerank_mirror_matches_the_weighted_sum(
    client: AppClient, auth: dict[str, str]
) -> None:
    body = _ranking(client, auth)
    row = dict_row(body)
    weights = as_mapping(body.get("weights"))
    # The fixture weights sum to 1.0; the formula is the plain weighted sum.
    expected = _weighted_sum(weights, row, CATEGORY_NAMES)
    assert client_final_score(weights, row) == pytest.approx(round(expected, 1))
    assert client_final_score(weights, row) == pytest.approx(78.9)


def dict_row(body: dict[str, Json]) -> dict[str, Json]:
    """The first ranked venture row of a ranking body.

    Args:
        body: The /v1/ranking response body.

    Returns:
        The row.
    """
    rows = body.get("ventures")
    assert isinstance(rows, list)
    return as_mapping(rows[0])


def _renormalized(
    weights: dict[str, Json], row: dict[str, Json], names: tuple[str, ...]
) -> float | None:
    parts: list[float] = [get_float(weights, f"w_{name}") or 0.0 for name in names]
    scored_weight = sum(parts)
    if scored_weight <= 0.0:
        return None
    return _weighted_sum(weights, row, names) / scored_weight


def test_rerank_mirror_renormalizes_when_a_category_is_unscored(
    client: AppClient, auth: dict[str, str]
) -> None:
    body = _ranking(client, auth)
    row = dict_row(body)
    row["s_traction"] = None
    weights = as_mapping(body.get("weights"))
    remaining = tuple(name for name in CATEGORY_NAMES if name != "traction")
    expected = _renormalized(weights, row, remaining)
    assert expected is not None
    assert client_final_score(weights, row) == pytest.approx(round(expected, 1))


def test_rerank_mirror_returns_none_without_weights(
    client: AppClient, auth: dict[str, str]
) -> None:
    row = dict_row(_ranking(client, auth))
    assert client_final_score({}, row) is None
