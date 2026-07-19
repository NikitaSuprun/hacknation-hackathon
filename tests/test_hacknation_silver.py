# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Golden-row tests: Hack Nation payloads render every silver.project column exactly."""

from datetime import UTC, datetime
from typing import Final

import pytest

from contracts.models import Json
from sources.hacknation.silver import MalformedProjectPayloadError, project_row
from tools import ddl_registry, ids

T_SCRAPED: Final[datetime] = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
T_UPDATED: Final[datetime] = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
SOURCE_URL: Final[str] = (
    "https://projects.hack-nation.ai/.netlify/functions/bff-projects-public-v2?id=hn-proj-001"
)

STRUCTURED: Final[dict[str, Json]] = {
    "problem": "Robot grasping is brittle.",
    "solution": "Foundation-model grasp synthesis.",
    "usp": "10x faster grasp synthesis.",
    "impact": "Warehouse automation.",
    "implementation": "PyTorch pipeline on Databricks.",
    "targetAudience": "Robotics integrators.",
    "jury_scope": "Best technical depth.",
}


def _payload() -> dict[str, Json]:
    return {
        "id": "hn-proj-001",
        "title": "GraspGen",
        "code": "GRASP",
        "summary": "Foundation-model grasping for warehouse robots.",
        "detail": "Longer pitch text.",
        "heroImage": "https://cdn.hack-nation.ai/hero/hn-proj-001.png",
        "ownerId": "u-100",
        "createdAt": "2026-06-01T10:00:00+00:00",
        "updatedAt": "2026-06-20T10:00:00+00:00",
        "category": "Robotics",
        "techStack": ["Python", "PyTorch"],
        "tags": ["robotics", "manipulation"],
        "eventId": "ev-1",
        "eventTitle": "Global AI Hackathon 2026",
        "challengeId": "ch-9",
        "challengeTitle": "Physical AI",
        "companyId": None,
        "companyName": None,
        "winner": True,
        "demoUrl": "https://graspgen.hack-nation.ai",
        "githubUrl": "https://github.com/grasplab/graspgen",
        "media": [],
        "structured": dict(STRUCTURED),
        "programType": "open",
        "authorProfile": {"userId": "u-100", "displayName": "Léna Fischer"},
        "team": [
            {"userId": "u-200", "displayName": "Marco Rossi", "role": "ML engineer"},
            {"displayName": "Ghost Member", "role": "advisor"},
        ],
        "review": None,
        "extra": None,
        "funMoment": None,
    }


def test_project_row_golden() -> None:
    row = project_row(_payload(), source_url=SOURCE_URL, scraped_at=T_SCRAPED, updated_at=T_UPDATED)
    assert row == {
        "project_id": ids.hacknation_project_id("hn-proj-001"),
        "repo_id": None,
        "full_name": None,
        "name": "GraspGen",
        "owner_login": None,
        "is_org_owned": None,
        "description": "Foundation-model grasping for warehouse robots.",
        "summary_ai": None,
        "market_tags": ["robotics", "manipulation"],
        "usp_notes": "10x faster grasp synthesis.",
        "primary_language": None,
        "languages": None,
        "topics": ["Python", "PyTorch"],
        "stars": None,
        "forks": None,
        "license": None,
        "homepage_url": "https://graspgen.hack-nation.ai",
        "source_platform": "hacknation",
        "github_url": "github.com/grasplab/graspgen",
        "structured": STRUCTURED,
        "event_title": "Global AI Hackathon 2026",
        "challenge_title": "Physical AI",
        "is_winner": True,
        "arxiv_ids_in_readme": None,
        "funding_signals": None,
        "is_corporate_oss": None,
        "is_academic": None,
        "venture_likeness": None,
        "contributor_count": 3,
        "created_at_source": datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        "pushed_at": None,
        "ai_model_version": None,
        "source_url": SOURCE_URL,
        "scraped_at": T_SCRAPED,
        "updated_at": T_UPDATED,
    }


def test_project_row_none_handling_for_sparse_payloads() -> None:
    row = project_row(
        {"id": "hn-x"}, source_url=SOURCE_URL, scraped_at=T_SCRAPED, updated_at=T_UPDATED
    )
    assert row["project_id"] == ids.hacknation_project_id("hn-x")
    assert row["structured"] is None
    assert row["github_url"] is None
    assert row["usp_notes"] is None
    assert row["market_tags"] == []
    assert row["topics"] == []
    assert row["contributor_count"] is None
    assert row["created_at_source"] is None
    assert row["is_winner"] is None
    assert row["name"] is None
    assert row["homepage_url"] is None


def test_created_at_parsing_is_tz_aware_and_junk_safe() -> None:
    naive = project_row(
        {"id": "hn-x", "createdAt": "2026-06-01T10:00:00"},
        source_url=SOURCE_URL,
        scraped_at=T_SCRAPED,
        updated_at=T_UPDATED,
    )
    assert naive["created_at_source"] == datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    junk = project_row(
        {"id": "hn-x", "createdAt": "yesterday"},
        source_url=SOURCE_URL,
        scraped_at=T_SCRAPED,
        updated_at=T_UPDATED,
    )
    assert junk["created_at_source"] is None


def test_contributor_count_without_author() -> None:
    row = project_row(
        {"id": "hn-x", "team": [{"userId": "u-200"}, {"role": "advisor"}]},
        source_url=SOURCE_URL,
        scraped_at=T_SCRAPED,
        updated_at=T_UPDATED,
    )
    assert row["contributor_count"] == 2


def test_column_set_matches_ddl_registry() -> None:
    row = project_row(_payload(), source_url=SOURCE_URL, scraped_at=T_SCRAPED, updated_at=T_UPDATED)
    schema = ddl_registry.table_schema("silver.project")
    assert set(row) == set(schema.column_names)


def test_malformed_payload_raises() -> None:
    with pytest.raises(MalformedProjectPayloadError):
        project_row("nope", source_url=SOURCE_URL, scraped_at=T_SCRAPED, updated_at=T_UPDATED)
    with pytest.raises(MalformedProjectPayloadError):
        project_row(
            {"title": "no id"}, source_url=SOURCE_URL, scraped_at=T_SCRAPED, updated_at=T_UPDATED
        )
