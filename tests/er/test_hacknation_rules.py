# Copyright (c) 2026 Venture Hunt. All rights reserved.
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
    expected = "linkedin.com/in/lena-fischer-robotics"
    assert linkedin_norm(fx.LENA_LINKEDIN_GITHUB_RAW) == expected
    assert linkedin_norm(fx.LENA_LINKEDIN_HN_RAW) == expected
    assert linkedin_norm("http://linkedin.com/in/lena-fischer-robotics?trk=x") == expected
    assert linkedin_norm("https://WWW.LinkedIn.com/in/Lena-Fischer-Robotics") == expected
    assert linkedin_norm(None) is None
    assert linkedin_norm("   ") is None


def test_d7_fires_on_linkedin_equality_across_url_spellings(inputs: ErInputs) -> None:
    views = [psr_view(row) for row in inputs.psr_rows]
    matches = {
        (match.left, match.right): match
        for match in deterministic_matches(views, {})
        if match.rule == "D7"
    }
    pair = _pair(fx.PSR_LENA_GITHUB, fx.PSR_LENA_HN)
    match = matches[pair]
    assert match.method == "det_linkedin"
    assert match.confidence == 0.97
    assert match.auto is True
    assert match.evidence == {"rule": "D7", "linkedin": "linkedin.com/in/lena-fischer-robotics"}
    # No other pair shares a LinkedIn URL in the fixture universe.
    assert set(matches) == {pair}


def test_d8_candidates_pair_hn_members_with_core_contributors(inputs: ErInputs) -> None:
    candidates = hacknation_repo_candidates(
        inputs.hacknation_projects, inputs.projects, inputs.contributions
    )
    url = "github.com/grasplab/grasp-anything"
    assert candidates == {
        _pair(fx.PSR_LENA_HN, fx.PSR_LENA_GITHUB): url,
        _pair(fx.PSR_WEI_HN, fx.PSR_LENA_GITHUB): url,
    }
    # Wei's github record (share 0.38) is below the core-contributor floor, so
    # he enters only as a project member, never as a candidate partner.
    assert all(fx.PSR_WEI_A_GITHUB not in key for key in candidates)


def test_d8_gates_on_name_jaro_winkler(inputs: ErInputs) -> None:
    views = {str(row["source_record_id"]): psr_view(row) for row in inputs.psr_rows}
    pair = _pair(fx.PSR_LENA_HN, fx.PSR_LENA_GITHUB)
    url = "github.com/grasplab/grasp-anything"
    (match,) = hacknation_matches(views, {pair: url})
    assert match.rule == "D8"
    assert match.method == "det_hn_repo"
    assert match.confidence == 0.9
    assert match.auto is True
    assert match.evidence == {"rule": "D8", "github_url": url, "name_jw": 1.0}
    # The same candidate against a dissimilar name never fires.
    dissimilar = _pair(fx.PSR_LENA_HN, fx.PSR_NILS_GITHUB)
    assert hacknation_matches(views, {dissimilar: url}) == []


def test_plugin_proof_partition_and_methods(scratch_outputs: ErOutputs) -> None:
    """HN5 acceptance: the engine links HN PSRs with zero engine edits."""
    links = {
        str(row["source_record_id"]): row
        for row in scratch_outputs.tables["silver.person_source_link"]
        if row["status"] == "active"
    }
    assert (
        str(links[fx.PSR_LENA_HN]["person_id"])
        == str(links[fx.PSR_LENA_GITHUB]["person_id"])
        == fx.LENA
    )
    # MASK (fixture drift): the fixtures narrate det_linkedin for the hacknation
    # link, but Lena's project entry repeats the ethz.ch address her github
    # profile carries, so D2 (0.98) outranks D7 (0.97) in the arbitration.
    assert links[fx.PSR_LENA_HN]["match_method"] == "det_email"
    # MASK (fixture drift): the fixtures narrate det_hn_repo for Wei, but D8
    # pairs him only with Lena's github record - she is the sole core
    # contributor of the pitched repo - and the name gate rejects that pair, so
    # his hackathon record reaches the cluster through the adjudication band.
    assert str(links[fx.PSR_WEI_HN]["person_id"]) == fx.WEI_A
    assert links[fx.PSR_WEI_HN]["match_method"] == "llm_adjudication"
    assert str(links[fx.PSR_SELIN_HN]["person_id"]) == fx.SELIN
    assert links[fx.PSR_SELIN_HN]["match_method"] == "seed_fixture"


def test_plugin_proof_survivorship_carries_linkedin_and_cv(
    scratch_outputs: ErOutputs,
) -> None:
    persons = {str(row["person_id"]): row for row in scratch_outputs.tables["silver.person"]}
    assert persons[fx.LENA]["linkedin_url"] == fx.LENA_LINKEDIN_GITHUB_RAW
    assert persons[fx.SELIN]["cv_url"] == fx.SELIN_CV_URL
    # Wei's hacknation record carries neither field: nothing appears from nowhere.
    assert persons[fx.WEI_A]["linkedin_url"] is None
    assert persons[fx.WEI_A]["cv_url"] is None


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
