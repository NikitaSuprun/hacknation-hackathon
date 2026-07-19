# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Thesis, weights, and ideal editors: persistence to the overlay and validation."""

import json
from typing import Final

from contracts.models import Json
from fixtures import build
from scrapers.common.jsonutil import as_mapping, get_str
from tests.app.conftest import AppClient

NEW_WEIGHTS: Final[dict[str, Json]] = {
    "w_individual_experience": 0.2,
    "w_schools": 0.05,
    "w_network_ties": 0.05,
    "w_prior_collaboration": 0.1,
    "w_problem_realness": 0.15,
    "w_product_defensibility": 0.15,
    "w_market": 0.1,
    "w_traction": 0.15,
    "w_ideal_match": 0.05,
}

VALID_IDEAL: Final[dict[str, Json]] = {
    "schema_version": 1,
    "narrative": "Hands-on robotics researcher turned founder.",
    "education": [{"institution": "ETH Zurich", "level": "PhD", "field": "robotics"}],
    "sectors": ["robotics"],
    "keywords": ["manipulation", "grasping"],
    "numeric_features": {"stars_weighted": 8.0},
    "feature_weights": {"stars_weighted": 1.0},
}


def test_weights_put_persists_to_the_overlay(client: AppClient, auth: dict[str, str]) -> None:
    response = client.put(
        f"/v1/thesis/{build.THESIS_ID}/weights", payload=NEW_WEIGHTS, headers=auth
    )
    assert response.status_code == 200
    stored = client.get("/v1/thesis", headers=auth).items("weights")[0]
    for key, value in NEW_WEIGHTS.items():
        assert stored[key] == value
    assert stored["updated_by"] == "app"
    # The ranking endpoint serves the updated weights to the sliders.
    ranking = client.get("/v1/ranking", headers=auth).body
    assert as_mapping(ranking.get("weights"))["w_traction"] == 0.15


def test_weights_put_rejects_missing_or_non_numeric_fields(
    client: AppClient, auth: dict[str, str]
) -> None:
    incomplete = dict(NEW_WEIGHTS)
    del incomplete["w_traction"]
    response = client.put(f"/v1/thesis/{build.THESIS_ID}/weights", payload=incomplete, headers=auth)
    assert response.status_code == 422
    assert "w_traction" in (get_str(response.body, "error") or "")


def test_weights_put_404s_for_an_unknown_thesis(client: AppClient, auth: dict[str, str]) -> None:
    response = client.put("/v1/thesis/nope/weights", payload=NEW_WEIGHTS, headers=auth)
    assert response.status_code == 404


def test_ideal_put_rejects_schema_invalid_payloads(client: AppClient, auth: dict[str, str]) -> None:
    invalid: dict[str, Json] = {"schema_version": 1, "education": [{"level": "PhD"}]}
    response = client.put(
        f"/v1/thesis/{build.THESIS_ID}/ideal-candidate", payload=invalid, headers=auth
    )
    assert response.status_code == 422
    errors = response.body.get("errors")
    assert isinstance(errors, list)
    messages = [error for error in errors if isinstance(error, str)]
    assert any("numeric_features" in message for message in messages)
    assert any("institution" in message for message in messages)


def test_ideal_put_persists_and_reembeds(client: AppClient, auth: dict[str, str]) -> None:
    response = client.put(
        f"/v1/thesis/{build.THESIS_ID}/ideal-candidate", payload=VALID_IDEAL, headers=auth
    )
    assert response.status_code == 200
    assert response.body["version"] == 2
    stored = client.get("/v1/thesis", headers=auth).items("ideals")[0]
    profile_text = stored["profile_json"]
    assert isinstance(profile_text, str)  # VARIANT crosses as a JSON string
    assert json.loads(profile_text) == VALID_IDEAL
    assert stored["embedding_model"] == "fixture-fake-embedding"
    assert "embedding" not in stored  # bulky vector stays server-side


def test_thesis_post_upserts_the_row(client: AppClient, auth: dict[str, str]) -> None:
    response = client.post(
        "/v1/thesis",
        payload={"thesis_id": build.THESIS_ID, "name": "Swiss deep-tech v2", "sectors": ["ai"]},
        headers=auth,
    )
    assert response.status_code == 200
    stored = client.get("/v1/thesis", headers=auth).items("theses")[0]
    assert stored["name"] == "Swiss deep-tech v2"
    assert stored["sectors"] == ["ai"]


def test_thesis_post_requires_a_name(client: AppClient, auth: dict[str, str]) -> None:
    assert client.post("/v1/thesis", payload={"notes": "x"}, headers=auth).status_code == 422
