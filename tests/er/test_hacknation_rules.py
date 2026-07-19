# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""WS-G: the D7/D8 rules and the plug-in proof over the full ER pipeline."""

from dataclasses import replace

from er.models import psr_view
from er.offline import offline_deps
from er.pipeline import ALL_STAGES, ErInputs, ErOutputs, run_pipeline
from er.rules import (
    deterministic_matches,
    hacknation_matches,
    hacknation_repo_candidates,
    linkedin_norm,
)
from fixtures import build as fx
from tests.er.conftest import as_json_rows


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def test_linkedin_norm_canonicalizes_scheme_www_slash_and_case() -> None:
    expected = "linkedin.com/in/mira-kovac"
    assert linkedin_norm("https://www.linkedin.com/in/mira-kovac/") == expected
    assert linkedin_norm("http://linkedin.com/in/mira-kovac?trk=x") == expected
    assert linkedin_norm("https://WWW.LinkedIn.com/in/Mira-Kovac") == expected
    assert linkedin_norm(None) is None
    assert linkedin_norm("   ") is None


def test_d7_fires_on_linkedin_equality_across_url_spellings(inputs: ErInputs) -> None:
    views = [psr_view(row) for row in inputs.psr_rows]
    matches = {
        (match.left, match.right): match
        for match in deterministic_matches(views, {})
        if match.rule == "D7"
    }
    pair = _pair(fx.PSR_MIRA_GITHUB, fx.PSR_MIRA_HACKNATION)
    match = matches[pair]
    assert match.method == "det_linkedin"
    assert match.confidence == 0.97
    assert match.auto is True
    assert match.evidence == {"rule": "D7", "linkedin": "linkedin.com/in/mira-kovac"}
    # No other pair shares a LinkedIn URL in the fixture universe.
    assert set(matches) == {pair}


def test_d8_candidates_pair_hn_members_with_core_contributors(inputs: ErInputs) -> None:
    candidates = hacknation_repo_candidates(
        inputs.hacknation_projects, inputs.projects, inputs.contributions
    )
    pair = _pair(fx.PSR_LENA_HACKNATION, fx.PSR_LENA_GITHUB)
    assert candidates == {pair: "github.com/grasplab/grasp-anything"}
    # Wei (share 0.38) is below the core-contributor floor: never a candidate.
    assert all(fx.PSR_WEI_A_GITHUB not in key for key in candidates)


def test_d8_gates_on_name_jaro_winkler(inputs: ErInputs) -> None:
    views = {str(row["source_record_id"]): psr_view(row) for row in inputs.psr_rows}
    pair = _pair(fx.PSR_LENA_HACKNATION, fx.PSR_LENA_GITHUB)
    url = "github.com/grasplab/grasp-anything"
    (match,) = hacknation_matches(views, {pair: url})
    assert match.rule == "D8"
    assert match.method == "det_github_contrib"
    assert match.confidence == 0.9
    assert match.auto is True
    assert match.evidence == {"rule": "D8", "github_url": url, "name_jw": 1.0}
    # The same candidate against a dissimilar name never fires.
    dissimilar = _pair(fx.PSR_LENA_HACKNATION, fx.PSR_NILS_GITHUB)
    assert hacknation_matches(views, {dissimilar: url}) == []


def test_plugin_proof_partition_and_methods(scratch_outputs: ErOutputs) -> None:
    """HN5 acceptance: the engine links HN PSRs with zero engine edits."""
    links = {
        str(row["source_record_id"]): row
        for row in scratch_outputs.tables["silver.person_source_link"]
        if row["status"] == "active"
    }
    assert str(links[fx.PSR_LENA_HACKNATION]["person_id"]) == fx.LENA
    assert links[fx.PSR_LENA_HACKNATION]["match_method"] == "det_github_contrib"
    assert (
        str(links[fx.PSR_MIRA_HACKNATION]["person_id"])
        == str(links[fx.PSR_MIRA_GITHUB]["person_id"])
        == fx.MIRA
    )
    assert links[fx.PSR_MIRA_HACKNATION]["match_method"] == "det_linkedin"
    assert links[fx.PSR_MIRA_GITHUB]["match_method"] == "det_linkedin"
    assert str(links[fx.PSR_NOAH_HACKNATION]["person_id"]) == fx.NOAH
    assert links[fx.PSR_NOAH_HACKNATION]["match_method"] == "seed_fixture"


def test_plugin_proof_survivorship_carries_linkedin_and_cv(
    scratch_outputs: ErOutputs,
) -> None:
    persons = {str(row["person_id"]): row for row in scratch_outputs.tables["silver.person"]}
    assert persons[fx.MIRA]["linkedin_url"] == fx.MIRA_LINKEDIN_GITHUB
    assert persons[fx.NOAH]["cv_url"] == fx.NOAH_CV_URL
    # Pre-WS-G persons stay untouched: no linkedin/cv appears from nowhere.
    assert persons[fx.LENA]["linkedin_url"] is None
    assert persons[fx.LENA]["cv_url"] is None


def test_rerun_with_hacknation_links_present_adds_nothing(
    inputs: ErInputs, scratch_outputs: ErOutputs
) -> None:
    rerun_inputs = replace(
        inputs,
        link_rows=as_json_rows(scratch_outputs.tables["silver.person_source_link"]),
        adjudication_rows=as_json_rows(scratch_outputs.tables["ops.llm_adjudications"]),
    )
    rerun = run_pipeline(rerun_inputs, offline_deps(inputs), stages=ALL_STAGES)
    assert rerun.tables["silver.person_source_link"] == []
