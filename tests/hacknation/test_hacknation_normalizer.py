"""Golden-value tests: Hack Nation bronze rows normalize byte-exact into PSR fragments."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Final

import pytest

from contracts.models import BronzeRecord, Json, SinkValue
from scrapers.hacknation import HacknationNormalizer, merge_psrs
from scrapers.hacknation.normalizer import psr_fragment_from_cv
from tools import ids

T_SCRAPED: Final[datetime] = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
T_INGESTED: Final[datetime] = datetime(2026, 7, 15, 8, 5, tzinfo=UTC)
T_SCRAPED_LATER: Final[datetime] = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
T_INGESTED_LATER: Final[datetime] = datetime(2026, 7, 16, 8, 5, tzinfo=UTC)

PEOPLE_URL: Final[str] = "https://projects.hack-nation.ai/.netlify/functions/bff-public-people-v2"
PROJECT_URL: Final[str] = (
    "https://projects.hack-nation.ai/.netlify/functions/bff-projects-public-v2?id=hn-proj-001"
)

LENA_ID: Final[str] = ids.psr_id("hacknation", "u-100")
MARCO_ID: Final[str] = ids.psr_id("hacknation", "u-200")


def _people_record(country: str = "Switzerland", tagline: str | None = None) -> BronzeRecord:
    row: dict[str, SinkValue] = {
        "user_id": "u-100",
        "payload": {
            "user_id": "u-100",
            "display_name": "Léna Fischer",
            "first_name": "Léna",
            "last_name": "Fischer",
            "avatar_url": "https://cdn.hack-nation.ai/avatars/u-100.png",
            "university": "ETH Zürich",
            "field_of_study": "Robotics",
            "academic_degree": "MSc",
            "professional_situation": "PhD student",
            "tagline": tagline if tagline is not None else "Robotics PhD building grasping.",
            "country": country,
            "city": "Zürich",
            "contributions": [{"id": "hn-proj-001", "title": "GraspGen"}],
        },
        "content_hash": "hash-people",
        "source_url": PEOPLE_URL,
        "scraped_at": T_SCRAPED,
        "ingested_at": T_INGESTED,
        "scrape_run_id": "run-001",
    }
    return BronzeRecord(table="bronze.hacknation_people_raw", row=row)


def _project_record() -> BronzeRecord:
    row: dict[str, SinkValue] = {
        "project_id": "hn-proj-001",
        "payload": {
            "id": "hn-proj-001",
            "title": "GraspGen",
            "summary": "Foundation-model grasping.",
            "ownerId": "u-100",
            "createdAt": "2026-06-01T10:00:00+00:00",
            "techStack": ["Python", "PyTorch", "Python", " "],
            "tags": ["robotics"],
            "eventTitle": "Global AI Hackathon",
            "challengeTitle": "Physical AI",
            "winner": True,
            "githubUrl": "https://github.com/grasplab/graspgen",
            "structured": {"usp": "10x faster grasp synthesis."},
            "authorProfile": {
                "userId": "u-100",
                "displayName": "Léna Fischer",
                "firstName": "Léna",
                "lastName": "Fischer",
                "email": "Lena.Fischer@ethz.ch",
                "linkedinUrl": "https://www.linkedin.com/in/lena-fischer/",
                "cvUrl": "https://cdn.hack-nation.ai/cvs/u-100.pdf",
                "avatarUrl": "https://cdn.hack-nation.ai/avatars/u-100.png",
                "university": "ETH Zürich",
                "fieldOfStudy": "Robotics",
                "city": "Zürich",
                "country": "CH",
            },
            "team": [
                {
                    "userId": "u-200",
                    "firstName": "Marco",
                    "lastName": "Rossi",
                    "email": "marco.rossi@grasplab.ch",
                    "university": "EPFL",
                    "role": "ML engineer",
                    "city": "Lausanne",
                    "country": "CH",
                },
                {"displayName": "Ghost Member", "role": "advisor"},
            ],
        },
        "content_hash": "hash-project",
        "source_url": PROJECT_URL,
        "scraped_at": T_SCRAPED_LATER,
        "ingested_at": T_INGESTED_LATER,
        "scrape_run_id": "run-002",
    }
    return BronzeRecord(table="bronze.hacknation_projects_raw", row=row)


def test_people_row_normalizes_golden() -> None:
    records = HacknationNormalizer().to_psr(_people_record())
    assert len(records) == 1
    record = records[0]
    assert record.source_record_id == LENA_ID
    assert record.source == "hacknation"
    assert record.source_key == "u-100"
    assert record.bronze_ref == "bronze.hacknation_people_raw:user_id=u-100"
    assert record.full_name == "Léna Fischer"
    assert record.name_norm == "lena fischer"
    assert record.first_name == "lena"
    assert record.last_name == "fischer"
    assert record.emails == ()
    assert record.email_norms == ()
    assert record.email_domain is None
    assert record.affiliation_raw == "ETH Zürich"
    assert record.org_norm == "eth zurich"
    assert record.location_raw == "Zürich, Switzerland"
    assert record.country_code is None
    assert record.keywords == ("Robotics",)
    assert record.bio == "Robotics PhD building grasping."
    assert record.avatar_url == "https://cdn.hack-nation.ai/avatars/u-100.png"
    assert record.cv_url is None
    assert record.source_url == PEOPLE_URL
    assert record.first_seen_at == T_SCRAPED
    assert record.last_seen_at == T_SCRAPED
    assert record.scraped_at == T_SCRAPED
    assert record.ingested_at == T_INGESTED


def test_people_row_two_letter_country_and_blank_strings() -> None:
    record = HacknationNormalizer().to_psr(_people_record(country="ch", tagline="   "))[0]
    assert record.country_code == "CH"
    assert record.location_raw == "Zürich"
    assert record.bio is None


def test_project_row_normalizes_author_and_team() -> None:
    records = HacknationNormalizer().to_psr(_project_record())
    assert len(records) == 2  # the ghost member has no userId and is skipped

    author = records[0]
    assert author.source_record_id == LENA_ID
    assert author.bronze_ref == "bronze.hacknation_projects_raw:project_id=hn-proj-001"
    assert author.full_name == "Léna Fischer"
    assert author.emails == ("Lena.Fischer@ethz.ch",)
    assert author.email_norms == ("lena.fischer@ethz.ch",)
    assert author.email_domain == "ethz.ch"
    assert author.linkedin_url == "linkedin.com/in/lena-fischer"
    assert author.cv_url == "https://cdn.hack-nation.ai/cvs/u-100.pdf"
    assert author.avatar_url == "https://cdn.hack-nation.ai/avatars/u-100.png"
    assert author.affiliation_raw == "ETH Zürich"
    assert author.org_norm == "eth zurich"
    assert author.keywords == ("Python", "PyTorch")
    assert author.location_raw == "Zürich"
    assert author.country_code == "CH"
    assert author.source_url == PROJECT_URL
    assert author.first_seen_at == T_SCRAPED_LATER
    assert author.last_seen_at == T_SCRAPED_LATER

    member = records[1]
    assert member.source_record_id == MARCO_ID
    assert member.full_name == "Marco Rossi"
    assert member.name_norm == "marco rossi"
    assert member.first_name == "marco"
    assert member.last_name == "rossi"
    assert member.emails == ("marco.rossi@grasplab.ch",)
    assert member.email_domain == "grasplab.ch"
    assert member.org_norm == "ecole polytechnique federale de lausanne"
    assert member.keywords == ("Python", "PyTorch")
    assert member.linkedin_url is None
    assert member.cv_url is None


def test_merge_psrs_collapses_fragments_per_person() -> None:
    normalizer = HacknationNormalizer()
    fragments = normalizer.to_psr(_people_record()) + normalizer.to_psr(_project_record())
    merged = merge_psrs(fragments)
    assert [record.source_record_id for record in merged] == sorted([LENA_ID, MARCO_ID])

    lena = next(record for record in merged if record.source_record_id == LENA_ID)
    assert lena.bio == "Robotics PhD building grasping."  # people fragment came first
    assert lena.location_raw == "Zürich, Switzerland"  # first non-null wins
    assert lena.country_code == "CH"  # people had None; project fills it
    assert lena.emails == ("Lena.Fischer@ethz.ch",)
    assert lena.email_norms == ("lena.fischer@ethz.ch",)
    assert lena.email_domain == "ethz.ch"
    assert lena.linkedin_url == "linkedin.com/in/lena-fischer"
    assert lena.cv_url == "https://cdn.hack-nation.ai/cvs/u-100.pdf"
    assert lena.keywords == ("Robotics", "Python", "PyTorch")  # ordered union
    assert lena.first_seen_at == T_SCRAPED
    assert lena.last_seen_at == T_SCRAPED_LATER
    assert lena.scraped_at == T_SCRAPED
    assert lena.bronze_ref == "bronze.hacknation_people_raw:user_id=u-100"

    marco = next(record for record in merged if record.source_record_id == MARCO_ID)
    assert marco.keywords == ("Python", "PyTorch")
    assert marco.first_seen_at == T_SCRAPED_LATER


def test_merge_psrs_recomputes_email_domain_from_merged_emails() -> None:
    normalizer = HacknationNormalizer()
    people = normalizer.to_psr(_people_record())[0]
    author = replace(normalizer.to_psr(_project_record())[0], email_domain=None)
    merged = merge_psrs([people, author])
    assert len(merged) == 1
    assert merged[0].email_domain == "ethz.ch"


def test_cv_fragment_carries_institutions_and_merges() -> None:
    extracted: Json = {
        "education": [
            {"institution": "ETH Zurich", "degree": "MSc"},
            {"institution": "  "},
            {"institution": "MIT"},
            {"degree": "BSc"},
        ],
        "experience": [],
        "skills": ["python"],
    }
    fragment = psr_fragment_from_cv(
        "u-100",
        extracted,
        source_url="https://cdn.hack-nation.ai/cvs/u-100.pdf",
        scraped_at=T_SCRAPED_LATER,
        ingested_at=T_INGESTED_LATER,
    )
    assert fragment is not None
    assert fragment.source_record_id == LENA_ID
    assert fragment.bronze_ref == "bronze.hacknation_cvs_raw:user_id=u-100"
    assert fragment.keywords == ("ETH Zurich", "MIT")
    assert fragment.full_name is None
    assert fragment.emails == ()

    people = HacknationNormalizer().to_psr(_people_record())[0]
    merged = merge_psrs([people, fragment])
    assert len(merged) == 1
    assert merged[0].keywords == ("Robotics", "ETH Zurich", "MIT")
    assert merged[0].full_name == "Léna Fischer"


def test_cv_fragment_is_none_without_institutions() -> None:
    cases: tuple[Json, ...] = ({"education": []}, {"education": "junk"}, {}, None)
    for extracted in cases:
        assert (
            psr_fragment_from_cv(
                "u-100",
                extracted,
                source_url="https://cdn.hack-nation.ai/cvs/u-100.pdf",
                scraped_at=T_SCRAPED,
                ingested_at=T_INGESTED,
            )
            is None
        )


def test_unknown_table_raises() -> None:
    record = BronzeRecord(table="bronze.github_users_raw", row={})
    with pytest.raises(ValueError, match="cannot normalize"):
        HacknationNormalizer().to_psr(record)
