# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Funding backbone: static list, SOGC capital increase, tri-state signal."""

from datetime import date

from contracts.models import CompanyRef, LLMResponse, PersonRef
from fixtures import build
from fixtures.fake_embedding import fake_embedding
from scoring.deps import ScoringDeps
from scoring.funding import (
    SIGNAL_CONFIRMED,
    SIGNAL_NONE,
    FundingProbe,
    StaticCascadeFundedFounderResolver,
    classify_funding_signal,
    interview_funding_signal,
)
from scoring.snapshot import Row, SilverSnapshot
from tools.llm import ScriptedLLMClient


def person_ref(person_id: str) -> PersonRef:
    return PersonRef(
        person_id=person_id,
        full_name=None,
        github_login=None,
        orcid=None,
        website_url=None,
        linkedin_url=None,
    )


def resolver(silver: SilverSnapshot) -> StaticCascadeFundedFounderResolver:
    return StaticCascadeFundedFounderResolver(
        list(silver.sogc), list(silver.officers), list(silver.companies)
    )


def test_jonas_keller_resolves_funded_via_static_list(silver: SilverSnapshot) -> None:
    status = resolver(silver).resolve(person_ref(build.JONAS_LAW))
    assert status.funded is True
    assert status.source == "static_list"


def test_grasplab_and_lena_are_not_funded(silver: SilverSnapshot) -> None:
    cascade = resolver(silver)
    grasp = CompanyRef(company_id=build.GRASP_COMPANY, uid=build.GRASP_UID, name="GraspLab AG")
    assert cascade.resolve(grasp).funded is False
    assert cascade.resolve(person_ref(build.LENA)).funded is False


def test_hr02_capital_increase_marks_company_funded(silver: SilverSnapshot) -> None:
    hr02: Row = {
        "sogc_id": "SHAB-2026-009999",
        "uid": build.GRASP_UID,
        "published_date": "2026-07-01",
        "sub_rubric": "HR02",
        "payload": {"publicationText": "GraspLab AG. Kapitalerhöhung auf CHF 250'000."},
    }
    cascade = StaticCascadeFundedFounderResolver(
        [hr02], list(silver.officers), list(silver.companies)
    )
    grasp = CompanyRef(company_id=build.GRASP_COMPANY, uid=build.GRASP_UID, name="GraspLab AG")
    status = cascade.resolve(grasp)
    assert status.funded is True
    assert status.source == "sogc_capital_increase"
    assert status.as_of == date(2026, 7, 1)
    # The text pattern alone also fires, independent of the rubric code.
    text_only = dict(hr02)
    text_only["sub_rubric"] = "HR01"
    cascade = StaticCascadeFundedFounderResolver([text_only], [], list(silver.companies))
    assert cascade.resolve(grasp).funded is True


def test_grasp_probe_classifies_none_found(silver: SilverSnapshot, deps: ScoringDeps) -> None:
    grasp = CompanyRef(company_id=build.GRASP_COMPANY, uid=build.GRASP_UID, name="GraspLab AG")
    probe = FundingProbe(
        venture_id=build.GRASP_VENTURE,
        company=grasp,
        texts=("Foundation models for robotic grasping",),
        source_url="https://grasplab.ch",
    )
    signal, evidence = classify_funding_signal(probe, resolver(silver), deps.llm)
    assert signal == SIGNAL_NONE
    assert evidence == []


def test_vocabulary_hit_is_confirmed_through_the_llm(silver: SilverSnapshot) -> None:
    confirm = LLMResponse(
        text='{"verdict": "confirmed_funded"}',
        parsed={"verdict": "confirmed_funded"},
        model="scripted",
    )
    llm = ScriptedLLMClient(
        {"TASK:funding_confirm venture=v-test": confirm}, embedder=fake_embedding
    )
    probe = FundingProbe(
        venture_id="v-test",
        company=None,
        texts=("We raised a seed round backed by investors.",),
        source_url="https://example.com",
    )
    signal, evidence = classify_funding_signal(probe, resolver(silver), llm)
    assert signal == SIGNAL_CONFIRMED
    assert evidence
    assert evidence[0].source_type == "text_heuristic"


def test_funded_company_short_circuits_to_confirmed(
    silver: SilverSnapshot, deps: ScoringDeps
) -> None:
    keller = CompanyRef(
        company_id=build.KELLER_COMPANY, uid=build.KELLER_UID, name="Keller Advisory GmbH"
    )
    probe = FundingProbe(
        venture_id="v-keller", company=keller, texts=(), source_url="https://example.com"
    )
    signal, evidence = classify_funding_signal(probe, resolver(silver), deps.llm)
    assert signal == SIGNAL_CONFIRMED
    assert evidence
    assert evidence[0].source_type == "static_list"


def test_interview_funding_signal_maps_the_answer() -> None:
    assert interview_funding_signal({"funding_status": {"raised_before": False}}) == SIGNAL_NONE
    assert interview_funding_signal({"funding_status": {"raised_before": True}}) == SIGNAL_CONFIRMED
    assert interview_funding_signal({}) is None
