# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Funded-signal battery: planted READMEs fire, near-miss words never do."""

from typing import Final

from contracts.models import Json
from scrapers.github.signals import funded_signals, org_signals, readme_signals

PLANTED: Final[str] = (
    "We are backed by a16z and closed our Series A after a pre-seed in 2025. YC W25."
)


def test_planted_readme_fires_at_least_two_signals() -> None:
    fired = readme_signals(PLANTED)
    assert set(fired) >= {"backed_by", "a16z", "series_round", "preseed", "yc_batch"}


def test_word_boundaries_prevent_near_miss_matches() -> None:
    assert readme_signals("An accelerated pipeline for reseeding experiments.") == []
    assert readme_signals("The lightspeedster tool") == []
    assert readme_signals("sequoias are trees") == []


def test_yc_batch_is_case_sensitive() -> None:
    assert readme_signals("YC W25 company") == ["yc_batch"]
    assert readme_signals("yc w25 company") == []


def test_org_signals_from_owner_fields() -> None:
    repo: dict[str, Json] = {
        "homepageUrl": "https://fx01.dev/",
        "fundingLinks": [{"platform": "CUSTOM", "url": "https://fx01.dev/sponsor"}],
        "owner": {
            "__typename": "Organization",
            "isVerified": True,
            "websiteUrl": "https://www.fx01.dev",
        },
    }
    assert org_signals(repo) == ["org_verified", "funding_links", "org_domain_matches_homepage"]


def test_funded_signals_merges_and_dedupes() -> None:
    repo: dict[str, Json] = {"owner": {"isVerified": True}, "fundingLinks": []}
    fired = funded_signals(repo, "Backed by a16z. backed by everyone.")
    assert fired == ["backed_by", "a16z", "org_verified"]


def test_no_readme_means_org_signals_only() -> None:
    assert funded_signals({"owner": {}}, None) == []
