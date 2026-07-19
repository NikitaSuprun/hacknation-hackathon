# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Candidate pool: golden bytes plus thesis mutations flipping inclusion."""

from contracts.models import Json
from scoring.deps import ScoringDeps
from scoring.funding import SIGNAL_CONFIRMED, StaticCascadeFundedFounderResolver
from scoring.pool import (
    PoolAssembly,
    PoolCandidate,
    build_candidate_pool,
    pool_candidates,
)
from scoring.scripted import FIXTURE_NOW
from scoring.serialize import to_jsonl_lines
from scoring.snapshot import GoldInputs, SilverSnapshot
from tests.scoring.conftest import golden_text


def assembly(silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps) -> PoolAssembly:
    return PoolAssembly(
        ventures=gold.ventures,
        members=gold.members,
        projects=silver.projects,
        companies=silver.companies,
        resolver=StaticCascadeFundedFounderResolver(
            list(silver.sogc), list(silver.officers), list(silver.companies)
        ),
        llm=deps.llm,
    )


def test_pool_rows_byte_reproduce_golden_file(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    candidates = pool_candidates(assembly(silver, gold, deps))
    rows = build_candidate_pool(gold.theses[0], candidates, FIXTURE_NOW)
    assert to_jsonl_lines(rows) == golden_text("gold.candidate_pool")


def mutated_thesis(gold: GoldInputs, **changes: Json) -> dict[str, Json]:
    thesis = dict(gold.theses[0])
    thesis.update(changes)
    return thesis


def test_sector_mutation_flips_inclusion(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    candidates = pool_candidates(assembly(silver, gold, deps))
    rows = build_candidate_pool(mutated_thesis(gold, sectors=["fintech"]), candidates, FIXTURE_NOW)
    assert rows[0]["included"] is False
    assert rows[0]["exclusion_reasons"] == ["sector_mismatch"]


def test_team_size_mutation_flips_inclusion(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    candidates = pool_candidates(assembly(silver, gold, deps))
    rows = build_candidate_pool(mutated_thesis(gold, max_team=1), candidates, FIXTURE_NOW)
    assert rows[0]["included"] is False
    assert rows[0]["exclusion_reasons"] == ["team_too_large"]
    rows = build_candidate_pool(mutated_thesis(gold, min_team=5), candidates, FIXTURE_NOW)
    assert rows[0]["exclusion_reasons"] == ["team_too_small"]


def test_confirmed_funding_excludes_when_no_prior_vc_required(gold: GoldInputs) -> None:
    funded = PoolCandidate(
        venture_id="v-funded",
        market_tags=("robotics",),
        team_size=2,
        country_code="CH",
        is_corporate_oss=False,
        funding_signal=SIGNAL_CONFIRMED,
    )
    rows = build_candidate_pool(gold.theses[0], [funded], FIXTURE_NOW)
    assert rows[0]["included"] is False
    assert rows[0]["exclusion_reasons"] == ["confirmed_funded"]
    assert rows[0]["funding_signal"] == SIGNAL_CONFIRMED
    relaxed = build_candidate_pool(
        mutated_thesis(gold, require_no_prior_vc=False), [funded], FIXTURE_NOW
    )
    assert relaxed[0]["included"] is True


def test_corporate_oss_excluded_by_default(gold: GoldInputs) -> None:
    corporate = PoolCandidate(
        venture_id="v-corp",
        market_tags=("robotics",),
        team_size=2,
        country_code="CH",
        is_corporate_oss=True,
        funding_signal="none_found",
    )
    rows = build_candidate_pool(gold.theses[0], [corporate], FIXTURE_NOW)
    assert rows[0]["exclusion_reasons"] == ["corporate_oss"]


def test_unknown_geography_passes_but_mismatch_excludes(gold: GoldInputs) -> None:
    def candidate(country: str | None) -> PoolCandidate:
        return PoolCandidate(
            venture_id="v-geo",
            market_tags=("robotics",),
            team_size=2,
            country_code=country,
            is_corporate_oss=False,
            funding_signal="none_found",
        )

    unknown = build_candidate_pool(gold.theses[0], [candidate(None)], FIXTURE_NOW)
    assert unknown[0]["included"] is True
    eu_member = build_candidate_pool(gold.theses[0], [candidate("DE")], FIXTURE_NOW)
    assert eu_member[0]["included"] is True  # DE matches the EU geography
    offshore = build_candidate_pool(gold.theses[0], [candidate("US")], FIXTURE_NOW)
    assert offshore[0]["exclusion_reasons"] == ["geo_mismatch"]
