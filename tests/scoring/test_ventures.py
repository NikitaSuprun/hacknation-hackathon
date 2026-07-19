# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Venture builder: golden bytes, likeness gate, merge rules, member roles."""

import json

from contracts.models import LLMResponse
from fixtures import build
from fixtures.fake_embedding import fake_embedding
from scoring.deps import ScoringDeps
from scoring.serialize import to_jsonl_lines
from scoring.snapshot import GoldInputs, SilverSnapshot
from scoring.ventures import (
    VENTURE_LIKENESS_MIN,
    VentureBuild,
    build_ventures,
    classify_repo_likeness,
    hackathon_extras,
    strip_legal_suffix,
)
from tests.scoring.conftest import golden_text
from tools.llm import ScriptedLLMClient


def built(silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps) -> VentureBuild:
    return build_ventures(silver, gold.ventures, deps.llm, deps.clock)


def test_venture_rows_byte_reproduce_golden_files(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    result = built(silver, gold, deps)
    assert to_jsonl_lines(result.venture_rows) == golden_text("gold.venture")
    assert to_jsonl_lines(result.member_rows) == golden_text("gold.venture_member")


def test_likeness_gate_drops_fastsim_and_noise(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    result = built(silver, gold, deps)
    anchor_ids = {str(row["anchor_id"]) for row in result.venture_rows}
    # GraspLab plus the repo-less CareLoop; GraspOS Studio merges into the repo
    # anchor via its githubUrl instead of anchoring its own venture.
    assert anchor_ids == {build.GRASP_PROJECT, build.HN_P2_PROJECT}
    assert build.FASTSIM_PROJECT not in anchor_ids  # 0.55 < the 0.6 gate
    assert build.HN_P1_PROJECT not in anchor_ids


def test_merge_uses_earliest_anchor_and_company_name(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    row = built(silver, gold, deps).venture_rows[0]
    assert row["venture_id"] == build.GRASP_VENTURE
    assert row["anchor_type"] == "repo"  # repo created before the incorporation
    assert row["name"] == "GraspLab"  # company name minus the legal suffix
    assert row["status"] == "interviewing"  # lifecycle passthrough from prior gold


def test_member_roles_weights_and_evidence(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    members = built(silver, gold, deps).member_rows
    lena, wei = members[0], members[1]
    assert lena["person_id"] == build.LENA
    assert lena["weight"] == 0.62
    assert lena["role_hint"] == "founder"
    assert lena["is_founder_guess"] is True
    assert lena["evidence"] == {
        "contribution_share": 0.62,
        "officer_role": "founder",
        "hacknation_author": build.HN_P1_ID,
    }
    assert wei["person_id"] == build.WEI_A
    assert wei["weight"] == 0.38
    assert wei["role_hint"] == "maintainer"
    assert wei["evidence"] == {"contribution_share": 0.38, "hacknation_role": "ML Engineer"}


def test_new_venture_defaults_to_sourced_without_prior(
    silver: SilverSnapshot, deps: ScoringDeps
) -> None:
    result = build_ventures(silver, (), deps.llm, deps.clock)
    row = result.venture_rows[0]
    assert row["status"] == "sourced"
    assert row["quality_tier"] is None


def test_repo_likeness_orders_products_above_noise() -> None:
    fixture_repos = (
        ("grasp-anything", "Foundation models for robotic grasping", "Paper: arXiv:2506.11111"),
        ("fastsim", "Differentiable physics simulator", "Paper: arXiv:2507.22222"),
        ("awesome-robot-learning", "Curated list of robot learning resources", None),
        ("cs-101-exercises", "Course exercises for CS101", None),
        ("dotfiles", "My dotfiles", None),
    )
    scores = {
        name: classify_repo_likeness(name, description, readme)
        for name, description, readme in fixture_repos
    }
    products = (scores["grasp-anything"], scores["fastsim"])
    noise = (
        scores["awesome-robot-learning"],
        scores["cs-101-exercises"],
        scores["dotfiles"],
    )
    assert min(products) >= VENTURE_LIKENESS_MIN
    assert max(noise) < VENTURE_LIKENESS_MIN
    assert min(products) > max(noise)


def test_strip_legal_suffix_variants() -> None:
    assert strip_legal_suffix("GraspLab AG") == "GraspLab"
    assert strip_legal_suffix("Keller Advisory GmbH") == "Keller Advisory"
    assert strip_legal_suffix("AG") == "AG"  # never empty


def test_corporate_oss_projects_are_gated(silver: SilverSnapshot, deps: ScoringDeps) -> None:
    projects = tuple(
        dict(row) | {"is_corporate_oss": True} if row["project_id"] == build.GRASP_PROJECT else row
        for row in silver.projects
    )
    mutated = SilverSnapshot(
        projects=projects,
        companies=silver.companies,
        publications=silver.publications,
        contributions=silver.contributions,
        authorships=silver.authorships,
        officers=silver.officers,
        persons=silver.persons,
        connections=silver.connections,
        sogc=silver.sogc,
        hacknation_projects=silver.hacknation_projects,
        person_links=silver.person_links,
    )
    summary = LLMResponse(text="A venture.", parsed=None, model="scripted")
    llm = ScriptedLLMClient({}, embedder=fake_embedding, default=summary)
    result = build_ventures(mutated, (), llm, deps.clock)
    assert all(row["anchor_id"] != build.GRASP_PROJECT for row in result.venture_rows)


def test_member_rows_round_trip_via_json(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    lines = to_jsonl_lines(built(silver, gold, deps).member_rows).splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [row["person_id"] for row in parsed] == [build.LENA, build.WEI_A, build.SELIN]


def test_hackathon_merge_keeps_grasplab_member_set(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    # HN3 acceptance, merge side: GraspOS Studio's githubUrl merges it into the
    # GraspLab repo venture, and because both its members (Lena, Wei) already
    # contribute there the member set stays exactly {Lena, Wei}.
    result = built(silver, gold, deps)
    grasp_members = [row for row in result.member_rows if row["venture_id"] == build.GRASP_VENTURE]
    assert [row["person_id"] for row in grasp_members] == [build.LENA, build.WEI_A]
    venture_ids = [str(row["venture_id"]) for row in result.venture_rows]
    assert venture_ids.count(build.GRASP_VENTURE) == 1


def test_hackathon_only_project_becomes_its_own_venture(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    # HN3 acceptance, standalone side: CareLoop has no repo and anchors a new
    # hackathon_project venture with its author resolved through the ER links.
    result = built(silver, gold, deps)
    (careloop,) = [row for row in result.venture_rows if row["venture_id"] == build.SELIN_VENTURE]
    assert careloop["anchor_type"] == "hackathon_project"
    assert careloop["anchor_id"] == build.HN_P2_PROJECT
    assert careloop["name"] == "CareLoop"
    assert careloop["market_tags"] == ["health", "ai"]
    assert careloop["website_url"] is None  # neither a demoUrl nor a githubUrl
    (selin,) = [row for row in result.member_rows if row["venture_id"] == build.SELIN_VENTURE]
    assert selin["person_id"] == build.SELIN
    assert selin["role_hint"] == "founder"
    assert selin["is_founder_guess"] is True
    assert selin["evidence"] == {"source": "hacknation", "role": "author"}
    assert selin["weight"] == 1.0  # sole member takes the whole venture


def test_hackathon_extras_carry_the_structured_pitch(
    silver: SilverSnapshot, gold: GoldInputs
) -> None:
    (careloop,) = [row for row in gold.ventures if row["venture_id"] == build.SELIN_VENTURE]
    extras = hackathon_extras(silver, careloop)
    assert extras["event_title"] == "HackNation Global AI Hackathon 2026"
    assert extras["winner"] is False
    assert extras["universities"] == ["KTH Royal Institute of Technology"]
    structured = extras["structured"]
    assert isinstance(structured, dict)
    assert structured["problem"] == "Discharge planning is coordinated over phone and fax"
    assert structured["jury_scope"] == "Healthcare Challenge finalist"
    (grasp,) = [row for row in gold.ventures if row["venture_id"] == build.GRASP_VENTURE]
    assert hackathon_extras(silver, grasp) == {}
