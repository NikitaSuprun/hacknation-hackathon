"""Memo endpoint: nine sections, cited bullets, missing-data markers."""

import json
from typing import Final

from contracts.models import Json
from fixtures import build
from scrapers.common.jsonutil import as_mapping, get_str
from tests.app.conftest import AppClient, dict_items

SECTION_KEYS: Final[set[str]] = {
    "company_snapshot",
    "investment_hypotheses",
    "swot",
    "team_and_history",
    "problem_and_product",
    "technology_and_defensibility",
    "market_tam_sam_som",
    "competition",
    "traction_and_kpis",
}


def _sections(client: AppClient, auth: dict[str, str]) -> dict[str, Json]:
    response = client.get(f"/v1/venture/{build.GRASP_VENTURE}/memo", headers=auth)
    assert response.status_code == 200
    assert response.body["is_latest"] is True
    text = response.body["sections"]
    assert isinstance(text, str)  # VARIANT crosses as a JSON string
    return as_mapping(json.loads(text))


def test_memo_serves_nine_sections_as_a_json_string(
    client: AppClient, auth: dict[str, str]
) -> None:
    assert set(_sections(client, auth)) >= SECTION_KEYS


def test_every_non_missing_bullet_carries_evidence(client: AppClient, auth: dict[str, str]) -> None:
    sections = _sections(client, auth)
    missing_fields: list[str] = []
    for key in SECTION_KEYS:
        section = as_mapping(sections[key])
        for bullet in dict_items(section.get("bullets")):
            if bullet.get("missing"):
                gap_field = get_str(bullet, "gap_field")
                assert gap_field, f"missing bullet without gap_field in {key}"
                missing_fields.append(gap_field)
                continue
            evidence = dict_items(bullet.get("evidence"))
            assert evidence, f"cited bullet without evidence in {key}"
            assert all(get_str(item, "source_url") for item in evidence)
    assert set(missing_fields) == {"market.tam", "traction.revenue"}


def test_memo_404s_for_an_unknown_venture(client: AppClient, auth: dict[str, str]) -> None:
    assert client.get("/v1/venture/nope/memo", headers=auth).status_code == 404


def test_team_endpoint_serves_the_view_contract(client: AppClient, auth: dict[str, str]) -> None:
    team = client.get(f"/v1/venture/{build.GRASP_VENTURE}/team", headers=auth).items("team")
    assert [get_str(member, "full_name") for member in team] == ["Léna Fischer", "Wei Zhang"]
    founder = team[0]
    assert founder["is_founder_guess"] is True
    assert founder["github_login"] == "lenafischer"
    evidence_text = founder["evidence"]
    assert isinstance(evidence_text, str)  # VARIANT crosses as a JSON string
    assert as_mapping(json.loads(evidence_text))["officer_role"] == "founder"


def test_scores_endpoint_serves_history_latest_first(
    client: AppClient, auth: dict[str, str]
) -> None:
    scores = client.get(f"/v1/venture/{build.GRASP_VENTURE}/scores", headers=auth).items("scores")
    assert len(scores) == 2
    assert scores[0]["is_latest"] is True
    assert scores[0]["final_score"] == 78.4
    assert isinstance(scores[0]["breakdown"], str)
