# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Golden-row tests for the Hack Nation bronze row-builders."""

from datetime import UTC, datetime
from typing import Final

import pytest

from contracts.models import Json
from sources.hacknation.bronze import (
    MissingIdentifierError,
    PayloadShapeError,
    people_rows,
    project_row,
)
from tools.db import content_hash

_SCRAPED_AT: Final[datetime] = datetime(2026, 7, 19, 8, 30, tzinfo=UTC)
_INGESTED_AT: Final[datetime] = datetime(2026, 7, 19, 8, 31, tzinfo=UTC)
_RUN_ID: Final[str] = "run-20260719-a"

_PEOPLE_SOURCE_URL: Final[str] = (
    "https://projects.hack-nation.ai/.netlify/functions/bff-public-people-v2?limit=5000"
)

_ADA: Final[dict[str, Json]] = {
    "user_id": "u-ada",
    "display_name": "Ada Example",
    "first_name": "Ada",
    "last_name": "Example",
    "avatar_url": None,
    "university": "ETH Zurich",
    "field_of_study": "Computer Science",
    "academic_degree": "MSc",
    "professional_situation": "Student",
    "tagline": "Ships agents",
    "country": "Switzerland",
    "city": "Zurich",
}
_BEN: Final[dict[str, Json]] = {
    "user_id": "u-ben",
    "display_name": "Ben Example",
    "first_name": "Ben",
    "last_name": "Example",
}
_ADA_CONTRIBUTIONS: Final[list[Json]] = [{"id": "p-notary", "title": "AI Notary"}]
_PEOPLE_BODY: Final[dict[str, Json]] = {
    "data": {
        "people": [_ADA, _BEN],
        "contributionsByUserId": {"u-ada": _ADA_CONTRIBUTIONS},
    }
}

_PROJECT_DATA: Final[dict[str, Json]] = {
    "id": "9d1f7a2e-0000-4000-8000-000000000042",
    "title": "AI Notary",
    "code": "ai-notary",
    "summary": "Notarize agent output.",
    "githubUrl": "https://github.com/example/ai-notary",
    "winner": True,
    "techStack": ["python", "httpx"],
    "structured": {"problem": "Trust", "solution": "Hashes"},
    "authorProfile": {
        "userId": "u-ada",
        "displayName": "Ada Example",
        "email": "ada@example.org",
    },
    "team": [{"userId": "u-ben", "displayName": "Ben Example", "role": "Engineer"}],
}
_PROJECT_BODY: Final[dict[str, Json]] = {"data": _PROJECT_DATA, "meta": {"cache": "hit"}}


def test_people_rows_golden() -> None:
    rows = people_rows(
        _PEOPLE_BODY, scraped_at=_SCRAPED_AT, ingested_at=_INGESTED_AT, run_id=_RUN_ID
    )
    ada_payload: dict[str, Json] = {**_ADA, "contributions": _ADA_CONTRIBUTIONS}
    ben_payload: dict[str, Json] = {**_BEN, "contributions": []}
    assert rows == [
        {
            "user_id": "u-ada",
            "payload": ada_payload,
            "content_hash": content_hash(ada_payload),
            "source_url": _PEOPLE_SOURCE_URL,
            "scraped_at": _SCRAPED_AT,
            "ingested_at": _INGESTED_AT,
            "scrape_run_id": "run-20260719-a",
        },
        {
            "user_id": "u-ben",
            "payload": ben_payload,
            "content_hash": content_hash(ben_payload),
            "source_url": _PEOPLE_SOURCE_URL,
            "scraped_at": _SCRAPED_AT,
            "ingested_at": _INGESTED_AT,
            "scrape_run_id": "run-20260719-a",
        },
    ]


def test_people_rows_do_not_mutate_the_input() -> None:
    people_rows(_PEOPLE_BODY, scraped_at=_SCRAPED_AT, ingested_at=_INGESTED_AT, run_id=_RUN_ID)
    assert "contributions" not in _ADA
    assert "contributions" not in _BEN


def test_people_rows_missing_user_id_raises() -> None:
    body: dict[str, Json] = {
        "data": {"people": [{"display_name": "No Id"}], "contributionsByUserId": {}}
    }
    with pytest.raises(MissingIdentifierError, match="user_id"):
        people_rows(body, scraped_at=_SCRAPED_AT, ingested_at=_INGESTED_AT, run_id=_RUN_ID)


def test_people_rows_empty_user_id_raises() -> None:
    body: dict[str, Json] = {"data": {"people": [{"user_id": ""}], "contributionsByUserId": {}}}
    with pytest.raises(MissingIdentifierError, match="user_id"):
        people_rows(body, scraped_at=_SCRAPED_AT, ingested_at=_INGESTED_AT, run_id=_RUN_ID)


def test_people_rows_non_object_body_raises() -> None:
    with pytest.raises(PayloadShapeError, match="people-v2 body"):
        people_rows("<html>", scraped_at=_SCRAPED_AT, ingested_at=_INGESTED_AT, run_id=_RUN_ID)


def test_project_row_golden() -> None:
    row = project_row(
        _PROJECT_BODY, scraped_at=_SCRAPED_AT, ingested_at=_INGESTED_AT, run_id=_RUN_ID
    )
    assert row == {
        "project_id": "9d1f7a2e-0000-4000-8000-000000000042",
        "payload": _PROJECT_DATA,
        "content_hash": content_hash(_PROJECT_DATA),
        "source_url": (
            "https://projects.hack-nation.ai/.netlify/functions/"
            "bff-projects-public-v2?id=9d1f7a2e-0000-4000-8000-000000000042"
        ),
        "scraped_at": _SCRAPED_AT,
        "ingested_at": _INGESTED_AT,
        "scrape_run_id": "run-20260719-a",
    }


def test_project_row_missing_id_raises() -> None:
    body: dict[str, Json] = {"data": {"title": "No Id"}}
    with pytest.raises(MissingIdentifierError, match="'id'"):
        project_row(body, scraped_at=_SCRAPED_AT, ingested_at=_INGESTED_AT, run_id=_RUN_ID)


def test_project_row_empty_id_raises() -> None:
    body: dict[str, Json] = {"data": {"id": ""}}
    with pytest.raises(MissingIdentifierError, match="'id'"):
        project_row(body, scraped_at=_SCRAPED_AT, ingested_at=_INGESTED_AT, run_id=_RUN_ID)
