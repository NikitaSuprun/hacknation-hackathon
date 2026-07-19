# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Generate the fixture personas as JSONL, one file per table.

The fixtures are the executable contract: bronze payloads and their PSR rows
are built from the same constants through tools.norm/tools.ids, so WS-D's
golden-file requirement (bronze rows normalize byte-exact into these PSRs)
holds by construction. Personas exercise the ER rules: P1 golden path across
three sources, P2/P3 the unmergeable name twins, P4 commit-email, P5
ORCID-only, P6 the retracted-link unmerge shape, plus noise repos for the
venture-likeness gate. The Hack Nation trio (HN5 plug-in proof) replays its
bronze rows through the real sources.hacknation normalizer and silver builder:
D7 links Lena by LinkedIn, D8 links Wei by the pitched repo, and Selin arrives
as a new golden person with a parsed CV. Regenerate with `poe fixtures-build`;
drift against the committed files fails CI.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final, cast

from contracts.models import BronzeRecord, Json, PersonSourceRecord, SinkValue
from fixtures.fake_embedding import fake_embedding
from sources.hacknation.normalizer import HacknationNormalizer, merge_psrs, psr_fragment_from_cv
from sources.hacknation.silver import project_row as hacknation_project_row
from tools import ids, institutions, norm
from tools.db import content_hash
from tools.institutions import InstitutionRecord


class MissingInstitutionError(LookupError):
    """Raised when a fixture institution is absent from the ROR seed."""

    def __init__(self, query: str) -> None:
        """Name the unresolved institution."""
        super().__init__(f"{query} does not resolve; extend data/institutions/seed_queries.txt")


Row = dict[str, SinkValue]
Tables = dict[str, list[Row]]

DATA_DIR: Final[Path] = Path(__file__).resolve().parent / "data"

# One frozen clock for every fixture row: determinism beats realism here.
T_SCRAPED: Final[str] = "2026-07-15T08:00:00+00:00"
T_INGESTED: Final[str] = "2026-07-15T08:05:00+00:00"
T_UPDATED: Final[str] = "2026-07-15T09:00:00+00:00"
T_OLD_SCORE: Final[str] = "2026-07-12T09:00:00+00:00"
RUN_ID: Final[str] = "fixture-run-001"
PIPELINE_VERSION: Final[str] = "fixtures-1"

# Typed twins of the frozen clock: the real WS-G normalizer and silver builder
# take datetimes, and isoformat round-trips them byte-identical to the strings.
T_SCRAPED_DT: Final[datetime] = datetime.fromisoformat(T_SCRAPED)
T_INGESTED_DT: Final[datetime] = datetime.fromisoformat(T_INGESTED)
T_UPDATED_DT: Final[datetime] = datetime.fromisoformat(T_UPDATED)

# Golden persons: fixed v4-shaped literals so FKs read well in queries.
LENA: Final[str] = "11111111-1111-4111-8111-000000000001"
WEI_A: Final[str] = "22222222-2222-4222-8222-000000000002"
WEI_B: Final[str] = "33333333-3333-4333-8333-000000000003"
NILS: Final[str] = "44444444-4444-4444-8444-000000000004"
AISHA: Final[str] = "55555555-5555-4555-8555-000000000005"
JONAS_DEV: Final[str] = "66666666-6666-4666-8666-000000000006"
JONAS_LAW: Final[str] = "77777777-7777-4777-8777-000000000007"
SELIN: Final[str] = "88888888-8888-4888-8888-000000000008"

THESIS_ID: Final[str] = "aaaaaaaa-0000-4000-8000-000000000001"
WEIGHTS_ID: Final[str] = "aaaaaaaa-0000-4000-8000-000000000002"
IDEAL_ID: Final[str] = "aaaaaaaa-0000-4000-8000-000000000003"
SCORE_LATEST_ID: Final[str] = "bbbbbbbb-0000-4000-8000-000000000001"
SCORE_OLD_ID: Final[str] = "bbbbbbbb-0000-4000-8000-000000000002"
MEMO_ID: Final[str] = "bbbbbbbb-0000-4000-8000-000000000003"
OUTREACH_ID: Final[str] = "bbbbbbbb-0000-4000-8000-000000000004"
INTERVIEW_ID: Final[str] = "bbbbbbbb-0000-4000-8000-000000000005"
REVIEW_ID: Final[str] = "bbbbbbbb-0000-4000-8000-000000000006"
SCORE_CARELOOP_ID: Final[str] = "bbbbbbbb-0000-4000-8000-000000000007"

GRASP_REPO_ID: Final[int] = 910001
FASTSIM_REPO_ID: Final[int] = 910002
GRASP_PROJECT: Final[str] = ids.project_id(GRASP_REPO_ID)
FASTSIM_PROJECT: Final[str] = ids.project_id(FASTSIM_REPO_ID)
GRASP_VENTURE: Final[str] = ids.venture_id("repo", GRASP_PROJECT)
GRASP_UID: Final[str] = "CHE-123.456.789"
KELLER_UID: Final[str] = "CHE-987.654.321"
GRASP_COMPANY: Final[str] = ids.company_id(GRASP_UID)
KELLER_COMPANY: Final[str] = ids.company_id(KELLER_UID)
GRASP_ARXIV: Final[str] = "2506.11111"
BERGER_ARXIV: Final[str] = "2507.22222"
GRASP_PUBLICATION: Final[str] = ids.publication_id(None, GRASP_ARXIV, "W4400000001")
BERGER_PUBLICATION: Final[str] = ids.publication_id(None, BERGER_ARXIV, None)
SLAM_PUBLICATION: Final[str] = ids.publication_id(None, None, "W4400000002")

PSR_LENA_GITHUB: Final[str] = ids.psr_id("github", "501001")
PSR_LENA_OPENALEX: Final[str] = ids.psr_id("openalex_author", "A5000000001")
PSR_LENA_ZEFIX: Final[str] = ids.psr_id("zefix_officer", f"{GRASP_UID}:fischer lena")
PSR_WEI_A_OPENALEX: Final[str] = ids.psr_id("openalex_author", "A5000000002")
PSR_WEI_A_GITHUB: Final[str] = ids.psr_id("github", "501002")
PSR_WEI_B_OPENALEX: Final[str] = ids.psr_id("openalex_author", "A5000000003")
PSR_NILS_GITHUB: Final[str] = ids.psr_id("github", "501003")
PSR_NILS_ARXIV: Final[str] = ids.psr_id("arxiv_author", f"{BERGER_ARXIV}:1")
PSR_AISHA_OPENALEX: Final[str] = ids.psr_id("openalex_author", "A5000000005")
PSR_AISHA_ENRICHMENT: Final[str] = ids.psr_id("enrichment", "aisha-patel-site")
PSR_JONAS_GITHUB: Final[str] = ids.psr_id("github", "501006")
PSR_JONAS_ZEFIX: Final[str] = ids.psr_id("zefix_officer", f"{KELLER_UID}:keller jonas")

# Hack Nation (WS-G): three showcase identities and two projects; PSRs are
# generated by the real normalizer, so only keys and payloads live here.
HN_LENA_USER: Final[str] = "hn-lena-0001"
HN_WEI_USER: Final[str] = "hn-wei-0002"
HN_SELIN_USER: Final[str] = "hn-selin-0003"
HN_P1_ID: Final[str] = "5f1e6d3a-9c2b-4e51-8a7d-000000000001"
HN_P2_ID: Final[str] = "5f1e6d3a-9c2b-4e51-8a7d-000000000002"
PSR_LENA_HN: Final[str] = ids.psr_id("hacknation", HN_LENA_USER)
PSR_WEI_HN: Final[str] = ids.psr_id("hacknation", HN_WEI_USER)
PSR_SELIN_HN: Final[str] = ids.psr_id("hacknation", HN_SELIN_USER)
HN_P1_PROJECT: Final[str] = ids.hacknation_project_id(HN_P1_ID)
HN_P2_PROJECT: Final[str] = ids.hacknation_project_id(HN_P2_ID)
SELIN_VENTURE: Final[str] = ids.venture_id("hackathon_project", HN_P2_PROJECT)
HN_PEOPLE_URL: Final[str] = (
    "https://projects.hack-nation.ai/.netlify/functions/bff-public-people-v2?limit=5000"
)
HN_PROJECT_URL_PREFIX: Final[str] = (
    "https://projects.hack-nation.ai/.netlify/functions/bff-projects-public-v2?id="
)
# D7 spine: GitHub and Hack Nation spell Lena's LinkedIn differently on
# purpose; both collapse to one url_norm, which is the equality D7 matches on.
LENA_LINKEDIN_GITHUB_RAW: Final[str] = "https://linkedin.com/in/lena-fischer-robotics"
LENA_LINKEDIN_HN_RAW: Final[str] = "https://www.linkedin.com/in/lena-fischer-robotics/"
SELIN_CV_URL: Final[str] = "https://cdn.hack-nation.ai/cv/hn-selin-0003.pdf"
SELIN_CV_TEXT: Final[str] = "Selin Aydin\nKTH Royal Institute of Technology\nMSc Autonomous Systems"

IDEAL_TEXT: Final[str] = (
    "robotics manipulation grasping foundation models hardware founder open source"
)
LENA_TEXT: Final[str] = "robotic grasping manipulation foundation models open source robotics"
WEI_A_TEXT: Final[str] = "robot learning simulation reinforcement learning manipulation"

# The T3 blocked-write test key: a scraper upserting github user 999001 must be blocked.
SUPPRESSED_GITHUB_KEY: Final[str] = "999001"
SUPPRESSED_KEY_HASH: Final[str] = "80d14bf49f1a6242ce6ffce28f45a80c2c9bb2c82b113f30b5f92bf82a131824"
# Same shape for Hack Nation: an erased participant absent from bronze proves
# the suppression path covers the source (sha256 of the source key below).
HN_SUPPRESSED_KEY: Final[str] = "hn-erased-0009"
HN_SUPPRESSED_KEY_HASH: Final[str] = (
    "61e0794828548f57b2756f8e3fff06b385f2383f133a9b499771bde1f964d03f"
)


def _embedding(text: str) -> SinkValue:
    """Widen the embedding to a sink cell (list invariance blocks a direct pass)."""
    vector: SinkValue = list(fake_embedding(text))
    return vector


def _bronze_common(source_url: str, payload: SinkValue) -> Row:
    return {
        "payload": payload,
        "content_hash": content_hash(payload),
        "source_url": source_url,
        "scraped_at": T_SCRAPED,
        "ingested_at": T_INGESTED,
        "scrape_run_id": RUN_ID,
    }


def _github_bronze() -> Tables:
    grasp_payload: Row = {
        "name": "grasp-anything",
        "description": "Foundation models for robotic grasping",
        "stargazers_count": 8200,
        "forks_count": 410,
        "topics": ["robotics", "manipulation", "foundation-models"],
        "license": {"spdx_id": "Apache-2.0"},
        "homepage": "https://grasplab.ch",
        "created_at": "2026-03-05T10:00:00Z",
        "pushed_at": "2026-07-14T18:22:00Z",
        "readme_md": "GraspFM foundation models. Paper: arXiv:2506.11111. By GraspLab.",
    }
    fastsim_payload: Row = {
        "name": "fastsim",
        "description": "Differentiable physics simulator",
        "stargazers_count": 950,
        "topics": ["simulation"],
        "created_at": "2026-04-01T10:00:00Z",
        "pushed_at": "2026-07-10T11:00:00Z",
        "readme_md": "FastSim differentiable simulation. Paper: arXiv:2507.22222.",
    }
    noise = [
        (910003, "ml-hub/awesome-robot-learning", "Curated list of robot learning resources"),
        (910004, "uni-zh/cs-101-exercises", "Course exercises for CS101"),
        (910005, "someone/dotfiles", "My dotfiles"),
    ]
    repos: list[Row] = [
        {
            "repo_id": GRASP_REPO_ID,
            "full_name": "grasplab/grasp-anything",
            "etag": 'W/"grasp-1"',
            **_bronze_common("https://api.github.com/repos/grasplab/grasp-anything", grasp_payload),
        },
        {
            "repo_id": FASTSIM_REPO_ID,
            "full_name": "bergerlab/fastsim",
            "etag": 'W/"fastsim-1"',
            **_bronze_common("https://api.github.com/repos/bergerlab/fastsim", fastsim_payload),
        },
    ]
    for repo_id, full_name, description in noise:
        payload: Row = {"name": full_name.split("/")[1], "description": description}
        repos.append(
            {
                "repo_id": repo_id,
                "full_name": full_name,
                "etag": None,
                **_bronze_common(f"https://api.github.com/repos/{full_name}", payload),
            }
        )
    users: list[Row] = [
        {
            "user_id": 501001,
            "login": "lenafischer",
            **_bronze_common(
                "https://api.github.com/users/lenafischer",
                {
                    "name": "Léna Fischer",
                    "email": "lena.fischer@ethz.ch",
                    "company": "ETH Zürich",
                    "blog": "https://www.grasplab.ch/",
                    "location": "Zurich, Switzerland",
                    "bio": "Robotics PhD building foundation models for grasping.",
                    "avatar_url": "https://avatars.example.com/u/501001",
                },
            ),
        },
        {
            "user_id": 501002,
            "login": "weizhang-robotics",
            **_bronze_common(
                "https://api.github.com/users/weizhang-robotics",
                {
                    "name": "Wei Zhang",
                    "email": None,
                    "company": "ETH Zürich",
                    "location": "Zurich",
                    "bio": "Robot learning and simulation.",
                },
            ),
        },
        {
            "user_id": 501003,
            "login": "nilsberger",
            **_bronze_common(
                "https://api.github.com/users/nilsberger",
                {"name": "Nils Berger", "email": None, "company": None, "location": "Munich"},
            ),
        },
        {
            "user_id": 501006,
            "login": "jonaskeller",
            **_bronze_common(
                "https://api.github.com/users/jonaskeller",
                {"name": "Jonas Keller", "email": None, "location": "Berlin"},
            ),
        },
    ]
    commits: list[Row] = [
        {
            "repo_id": GRASP_REPO_ID,
            "sha": "c0ffee0000000000000000000000000000000001",
            "author_user_id": 501001,
            **_bronze_common(
                "https://api.github.com/repos/grasplab/grasp-anything/commits/c0ffee01",
                {
                    "author": {
                        "name": "Léna Fischer",
                        "email": "lena.fischer@ethz.ch",
                        "date": "2026-07-14T18:00:00Z",
                    },
                    "message": "Add grasp pose refinement",
                    "stats": {"additions": 420, "deletions": 60},
                },
            ),
        },
        {
            "repo_id": FASTSIM_REPO_ID,
            "sha": "c0ffee0000000000000000000000000000000002",
            "author_user_id": 501003,
            **_bronze_common(
                "https://api.github.com/repos/bergerlab/fastsim/commits/c0ffee02",
                {
                    "author": {
                        "name": "Nils Berger",
                        "email": "nils@berger.dev",
                        "date": "2026-07-10T10:30:00Z",
                    },
                    "message": "Vectorize contact solver",
                    "stats": {"additions": 210, "deletions": 35},
                },
            ),
        },
    ]
    for commit in commits:
        # Commits are immutable and keyed (repo_id, sha); the DDL carries no
        # change-detection hash for them.
        del commit["content_hash"]
    return {
        "bronze.github_repos_raw": repos,
        "bronze.github_users_raw": users,
        "bronze.github_commits_raw": commits,
    }


def _papers_bronze() -> Tables:
    arxiv: list[Row] = [
        {
            "arxiv_id": GRASP_ARXIV,
            "latest_version": 2,
            **_bronze_common(
                f"https://arxiv.org/abs/{GRASP_ARXIV}",
                {
                    "title": "GraspFM: Foundation Models for Robotic Grasping",
                    "abstract": "We present GraspFM. Code: github.com/grasplab/grasp-anything",
                    "authors": ["Léna Fischer", "Wei Zhang"],
                    "categories": ["cs.RO", "cs.LG"],
                    "comment": "Project page: https://grasplab.ch",
                },
            ),
        },
        {
            "arxiv_id": BERGER_ARXIV,
            "latest_version": 1,
            **_bronze_common(
                f"https://arxiv.org/abs/{BERGER_ARXIV}",
                {
                    "title": "FastSim: Differentiable Contact Simulation",
                    "abstract": "Differentiable physics. Code: github.com/bergerlab/fastsim",
                    "authors": ["Nils Berger"],
                    "categories": ["cs.RO"],
                    "comment": "Contact: nils@berger.dev",
                },
            ),
        },
    ]
    openalex: list[Row] = [
        {
            "openalex_id": "W4400000001",
            "doi": None,
            "arxiv_id": GRASP_ARXIV,
            **_bronze_common(
                "https://api.openalex.org/works/W4400000001",
                {
                    "title": "GraspFM: Foundation Models for Robotic Grasping",
                    "cited_by_count": 41,
                    "authorships": [
                        {
                            "author": {
                                "id": "A5000000001",
                                "display_name": "Léna Fischer",
                                "orcid": "https://orcid.org/0000-0002-1825-0097",
                            },
                            "institutions": [
                                {"ror": "https://ror.org/05a28rw58", "display_name": "ETH Zürich"}
                            ],
                            "author_position": "first",
                        },
                        {
                            "author": {
                                "id": "A5000000002",
                                "display_name": "Wei Zhang",
                                "orcid": None,
                            },
                            "institutions": [
                                {"ror": "https://ror.org/05a28rw58", "display_name": "ETH Zürich"}
                            ],
                            "author_position": "last",
                        },
                    ],
                },
            ),
        },
        {
            "openalex_id": "W4400000002",
            "doi": "10.1234/slam.2026.777",
            "arxiv_id": None,
            **_bronze_common(
                "https://api.openalex.org/works/W4400000002",
                {
                    "title": "Sparse Maps for Lifelong SLAM",
                    "cited_by_count": 12,
                    "authorships": [
                        {
                            "author": {
                                "id": "A5000000005",
                                "display_name": "A. Patel",
                                "orcid": "https://orcid.org/0000-0001-5109-3700",
                            },
                            "institutions": [
                                {
                                    "ror": "https://ror.org/026vcq606",
                                    "display_name": "KTH Royal Institute of Technology",
                                }
                            ],
                            "author_position": "first",
                        }
                    ],
                },
            ),
        },
    ]
    return {"bronze.arxiv_papers_raw": arxiv, "bronze.openalex_works_raw": openalex}


def _zefix_bronze() -> Tables:
    companies: list[Row] = [
        {
            "uid": GRASP_UID,
            "name": "GraspLab AG",
            **_bronze_common(
                f"https://www.zefix.admin.ch/api/v1/company/uid/{GRASP_UID}",
                {
                    "name": "GraspLab AG",
                    "legalForm": "AG",
                    "legalSeat": "Zürich",
                    "canton": "ZH",
                    "purpose": "Entwicklung und Vertrieb von Software für Robotergreifsysteme",
                    "status": "ACTIVE",
                    "sogcDate": "2026-06-20",
                    "address": {"street": "Technoparkstrasse 1", "zip": "8005", "town": "Zürich"},
                },
            ),
        },
        {
            "uid": KELLER_UID,
            "name": "Keller Advisory GmbH",
            **_bronze_common(
                f"https://www.zefix.admin.ch/api/v1/company/uid/{KELLER_UID}",
                {
                    "name": "Keller Advisory GmbH",
                    "legalForm": "GmbH",
                    "legalSeat": "Zug",
                    "canton": "ZG",
                    "purpose": "Beratung und Verwaltung von Beteiligungen",
                    "status": "ACTIVE",
                    "address": {"street": "Bahnhofstrasse 2", "zip": "6300", "town": "Zug"},
                },
            ),
        },
    ]
    sogc: list[Row] = [
        {
            "sogc_id": "SHAB-2026-001234",
            "uid": GRASP_UID,
            "published_date": "2026-06-20",
            "sub_rubric": "HR01",
            **_bronze_common(
                "https://amtsblattportal.ch/api/v1/publications/SHAB-2026-001234",
                {
                    "publicationText": (
                        "GraspLab AG, Zürich. Neueintragung. Eingetragene Personen: "
                        "Fischer, Léna, in Zürich, Mitglied des Verwaltungsrates, "
                        "mit Einzelunterschrift."
                    ),
                    "rubric": "HR",
                    "subRubric": "HR01",
                },
            ),
        }
    ]
    return {"bronze.zefix_companies_raw": companies, "bronze.zefix_sogc_raw": sogc}


def _hn_envelope(source_url: str, payload: dict[str, Json]) -> Row:
    """Bronze envelope with typed temporals so rows replay through the normalizer."""
    # Json is a semantic subset of SinkValue; the cast bridges the container
    # invariance the type system cannot see through (sources.hacknation.bronze
    # does the same).
    return {
        "payload": cast("SinkValue", payload),
        "content_hash": content_hash(payload),
        "source_url": source_url,
        "scraped_at": T_SCRAPED_DT,
        "ingested_at": T_INGESTED_DT,
        "scrape_run_id": RUN_ID,
    }


def _hn_graspos_payload() -> dict[str, Json]:
    """P1: the winning robotics project pitching the grasp-anything repo (D8)."""
    return {
        "id": HN_P1_ID,
        "title": "GraspOS Studio",
        "code": "GRASPOS",
        "summary": "No-code robot grasping workflows on grasp-anything",
        "category": "Robotics",
        "techStack": ["Python", "ROS2", "PyTorch"],
        "tags": ["robotics", "manipulation"],
        "eventTitle": "HackNation Global AI Hackathon 2026",
        "challengeTitle": "Embodied AI Challenge",
        "winner": True,
        "demoUrl": "https://graspos.demo.hack-nation.ai",
        "githubUrl": "https://github.com/grasplab/grasp-anything",
        "programType": "hackathon",
        "ownerId": HN_LENA_USER,
        "createdAt": "2026-06-20T10:00:00Z",
        "updatedAt": "2026-07-01T12:00:00Z",
        "structured": {
            "problem": "Robot grasping pipelines need weeks of engineering per cell",
            "solution": "No-code workflows on top of grasp-anything foundation models",
            "usp": "Only tool that ships sim-to-real grasp workflows in a day",
            "impact": "Cuts robot-cell integration from weeks to hours",
            "implementation": "ROS2 nodes orchestrated by a typed workflow DSL",
            "targetAudience": "Robotics integrators and lab automation teams",
            "jury_scope": "Won the Embodied AI Challenge jury award",
        },
        "authorProfile": {
            "userId": HN_LENA_USER,
            "displayName": "Léna Fischer",
            "firstName": "Léna",
            "lastName": "Fischer",
            "email": "lena.fischer@ethz.ch",
            "linkedinUrl": LENA_LINKEDIN_HN_RAW,
            "cvUrl": None,
            "avatarUrl": "https://cdn.hack-nation.ai/avatars/hn-lena-0001.png",
            "university": "ETH Zürich",
            "fieldOfStudy": "Robotics",
            "academicDegree": "PhD",
            "professionalSituation": "Founder",
            "city": "Zürich",
            "country": "Switzerland",
        },
        "team": [
            {
                "userId": HN_WEI_USER,
                "displayName": "Wei Zhang",
                "email": None,
                "linkedinUrl": None,
                "cvUrl": None,
                "avatarUrl": None,
                "university": "ETH Zürich",
                "fieldOfStudy": "Robot Learning",
                "academicDegree": "PhD",
                "professionalSituation": "Researcher",
                "city": "Zürich",
                "country": "Switzerland",
                "role": "ML Engineer",
            }
        ],
    }


def _hn_careloop_payload() -> dict[str, Json]:
    """P2: Selin's repo-less health project, the hackathon_project venture anchor."""
    return {
        "id": HN_P2_ID,
        "title": "CareLoop",
        "code": "CARELOOP",
        "summary": "Care-coordination copilot for hospital discharge planning",
        "category": "Health",
        "techStack": ["Python", "FastAPI", "React"],
        "tags": ["health", "ai"],
        "eventTitle": "HackNation Global AI Hackathon 2026",
        "challengeTitle": "Healthcare Challenge",
        "winner": False,
        "demoUrl": None,
        "githubUrl": None,
        "programType": "hackathon",
        "ownerId": HN_SELIN_USER,
        "createdAt": "2026-06-21T09:00:00Z",
        "updatedAt": "2026-07-02T15:00:00Z",
        "structured": {
            "problem": "Discharge planning is coordinated over phone and fax",
            "solution": "A copilot that drafts and tracks discharge care plans",
            "usp": "Integrates with hospital EHR export formats out of the box",
            "impact": "Frees nurse coordinators hours per patient",
            "implementation": "FastAPI service with an LLM planning core",
            "targetAudience": "Hospital discharge and case management teams",
            "jury_scope": "Healthcare Challenge finalist",
        },
        "authorProfile": {
            "userId": HN_SELIN_USER,
            "displayName": "Selin Aydın",  # noqa: RUF001 - Turkish dotless i is the real spelling
            "firstName": "Selin",
            "lastName": "Aydın",  # noqa: RUF001 - Turkish dotless i is the real spelling
            "email": "selin.aydin@careloop.se",
            "linkedinUrl": "https://www.linkedin.com/in/selin-aydin-kth",
            "cvUrl": SELIN_CV_URL,
            "avatarUrl": "https://cdn.hack-nation.ai/avatars/hn-selin-0003.png",
            "university": "KTH Royal Institute of Technology",
            "fieldOfStudy": "Autonomous Systems",
            "academicDegree": "MSc",
            "professionalSituation": "Founder",
            "city": "Stockholm",
            "country": "Sweden",
        },
        "team": [],
    }


def _selin_cv_extracted() -> dict[str, Json]:
    """The parsed-CV facts, shared by the bronze payload and the PSR fragment."""
    return {
        "education": [
            {
                "institution": "KTH Royal Institute of Technology",
                "degree": "MSc",
                "field": "Autonomous Systems",
                "start_year": 2023,
                "end_year": 2025,
            }
        ],
        "experience": [
            {
                "organization": "CareLoop",
                "title": "Co-founder",
                "start_year": 2026,
                "end_year": None,
                "summary": "Care coordination copilot",
            }
        ],
        "skills": ["python", "ros2", "clinical nlp"],
    }


def _selin_cv_payload() -> dict[str, Json]:
    """Mirror sources.hacknation.cv.cv_row's payload (parsed, so no raw_response)."""
    return {
        "cv_url": SELIN_CV_URL,
        "volume_path": f"/Volumes/dealflow_dev/ops/cv/hacknation/{HN_SELIN_USER}.pdf",
        "text_sha256": hashlib.sha256(SELIN_CV_TEXT.encode("utf-8")).hexdigest(),
        "text_chars": len(SELIN_CV_TEXT),
        "extracted": _selin_cv_extracted(),
        "model": "fixture",
    }


def _hacknation_bronze() -> Tables:
    lena_payload: dict[str, Json] = {
        "user_id": HN_LENA_USER,
        "display_name": "Léna Fischer",
        "university": "ETH Zürich",
        "field_of_study": "Robotics",
        "academic_degree": "PhD",
        "professional_situation": "Founder",
        "tagline": "Building grasp foundation models for anything",
        "country": "Switzerland",
        "city": "Zürich",
        "avatar_url": "https://cdn.hack-nation.ai/avatars/hn-lena-0001.png",
        "contributions": [{"id": HN_P1_ID, "title": "GraspOS Studio"}],
    }
    wei_payload: dict[str, Json] = {
        "user_id": HN_WEI_USER,
        "display_name": "Wei Zhang",
        "university": "ETH Zürich",
        "field_of_study": "Robot Learning",
        "academic_degree": "PhD",
        "professional_situation": "Researcher",
        "tagline": None,
        "country": "Switzerland",
        "city": "Zürich",
        "avatar_url": None,
        "contributions": [{"id": HN_P1_ID, "title": "GraspOS Studio"}],
    }
    selin_payload: dict[str, Json] = {
        "user_id": HN_SELIN_USER,
        "display_name": "Selin Aydın",  # noqa: RUF001 - Turkish dotless i is the real spelling
        "university": "KTH Royal Institute of Technology",
        "field_of_study": "Autonomous Systems",
        "academic_degree": "MSc",
        "professional_situation": "Founder",
        "tagline": "Care coordination copilot for hospitals",
        "country": "Sweden",
        "city": "Stockholm",
        "avatar_url": "https://cdn.hack-nation.ai/avatars/hn-selin-0003.png",
        "contributions": [{"id": HN_P2_ID, "title": "CareLoop"}],
    }
    people: list[Row] = [
        {"user_id": HN_LENA_USER, **_hn_envelope(HN_PEOPLE_URL, lena_payload)},
        {"user_id": HN_WEI_USER, **_hn_envelope(HN_PEOPLE_URL, wei_payload)},
        {"user_id": HN_SELIN_USER, **_hn_envelope(HN_PEOPLE_URL, selin_payload)},
    ]
    projects: list[Row] = [
        {
            "project_id": HN_P1_ID,
            **_hn_envelope(f"{HN_PROJECT_URL_PREFIX}{HN_P1_ID}", _hn_graspos_payload()),
        },
        {
            "project_id": HN_P2_ID,
            **_hn_envelope(f"{HN_PROJECT_URL_PREFIX}{HN_P2_ID}", _hn_careloop_payload()),
        },
    ]
    cvs: list[Row] = [
        {"user_id": HN_SELIN_USER, **_hn_envelope(SELIN_CV_URL, _selin_cv_payload())},
    ]
    return {
        "bronze.hacknation_people_raw": people,
        "bronze.hacknation_projects_raw": projects,
        "bronze.hacknation_cvs_raw": cvs,
    }


def _hacknation_psrs(bronze: Tables) -> list[Row]:
    """Hack Nation PSRs generated BY the real normalizer (the HN5 plug-in proof).

    People rows precede project rows, mirroring ingest order, so people-list
    values win survivorship; the CV fragment merges in last.
    """
    normalizer = HacknationNormalizer()
    fragments: list[PersonSourceRecord] = []
    for table in ("bronze.hacknation_people_raw", "bronze.hacknation_projects_raw"):
        for row in bronze[table]:
            fragments.extend(normalizer.to_psr(BronzeRecord(table=table, row=row)))
    cv_fragment = psr_fragment_from_cv(
        HN_SELIN_USER,
        _selin_cv_extracted(),
        source_url=SELIN_CV_URL,
        scraped_at=T_SCRAPED_DT,
        ingested_at=T_INGESTED_DT,
    )
    if cv_fragment is not None:
        fragments.append(cv_fragment)
    return [record.to_row() for record in merge_psrs(fragments)]


@dataclass(frozen=True, slots=True)
class PsrSeed:
    """Raw observed identity fields for one persona source record.

    Builder input only - contract value objects live in contracts.models -
    so empty defaults keep the persona definitions readable.
    """

    source: str
    source_key: str
    source_url: str
    bronze_ref: str | None = None
    full_name: str | None = None
    emails: tuple[str, ...] = ()
    orcid: str | None = None
    github_login: str | None = None
    website_url: str | None = None
    linkedin_url: str | None = None
    twitter_handle: str | None = None
    affiliation_raw: str | None = None
    location_raw: str | None = None
    country_code: str | None = None
    keywords: tuple[str, ...] = ()
    bio: str | None = None
    avatar_url: str | None = None
    cv_url: str | None = None


def make_psr(seed: PsrSeed) -> Row:
    """Derive the full PSR through the contract dataclass (byte-exact norms)."""
    email_norms = tuple(n for n in (norm.email_norm(e) for e in seed.emails) if n is not None)
    name_norm_value = norm.name_norm(seed.full_name) if seed.full_name else None
    parts = name_norm_value.split() if name_norm_value else []
    record = PersonSourceRecord(
        source_record_id=ids.psr_id(seed.source, seed.source_key),
        source=seed.source,
        source_key=seed.source_key,
        bronze_ref=seed.bronze_ref,
        full_name=seed.full_name,
        name_norm=name_norm_value,
        first_name=parts[0] if parts else None,
        last_name=parts[-1] if len(parts) > 1 else None,
        emails=seed.emails,
        email_norms=email_norms,
        email_domain=norm.email_domain(seed.emails[0]) if seed.emails else None,
        orcid=seed.orcid,
        github_login=seed.github_login,
        website_url_norm=norm.url_norm(seed.website_url) if seed.website_url else None,
        linkedin_url=seed.linkedin_url,
        twitter_handle=seed.twitter_handle,
        affiliation_raw=seed.affiliation_raw,
        org_norm=institutions.org_norm(seed.affiliation_raw) if seed.affiliation_raw else None,
        location_raw=seed.location_raw,
        country_code=seed.country_code,
        keywords=seed.keywords,
        bio=seed.bio,
        source_url=seed.source_url,
        first_seen_at=datetime.fromisoformat(T_SCRAPED),
        last_seen_at=datetime.fromisoformat(T_SCRAPED),
        scraped_at=datetime.fromisoformat(T_SCRAPED),
        ingested_at=datetime.fromisoformat(T_INGESTED),
        avatar_url=seed.avatar_url,
        cv_url=seed.cv_url,
    )
    return record.to_row()


def _person_source_records() -> list[Row]:
    return [
        make_psr(
            PsrSeed(
                source="github",
                source_key="501001",
                bronze_ref="bronze.github_users_raw:user_id=501001",
                full_name="Léna Fischer",
                emails=("lena.fischer@ethz.ch",),
                github_login="lenafischer",
                website_url="https://www.grasplab.ch/",
                linkedin_url=LENA_LINKEDIN_GITHUB_RAW,
                affiliation_raw="ETH Zürich",
                location_raw="Zurich, Switzerland",
                country_code="CH",
                keywords=("robotics", "grasping", "foundation-models"),
                bio="Robotics PhD building foundation models for grasping.",
                source_url="https://api.github.com/users/lenafischer",
            )
        ),
        make_psr(
            PsrSeed(
                source="openalex_author",
                source_key="A5000000001",
                bronze_ref="bronze.openalex_works_raw:openalex_id=W4400000001",
                full_name="Léna Fischer",
                orcid="0000-0002-1825-0097",
                affiliation_raw="ETH Zürich",
                country_code="CH",
                keywords=("robotics", "manipulation"),
                source_url="https://api.openalex.org/people/A5000000001",
            )
        ),
        make_psr(
            PsrSeed(
                source="zefix_officer",
                source_key=f"{GRASP_UID}:fischer lena",
                bronze_ref="bronze.zefix_sogc_raw:sogc_id=SHAB-2026-001234",
                full_name="Léna Fischer",
                affiliation_raw="GraspLab AG",
                location_raw="Zürich",
                country_code="CH",
                source_url="https://amtsblattportal.ch/api/v1/publications/SHAB-2026-001234",
            )
        ),
        make_psr(
            PsrSeed(
                source="openalex_author",
                source_key="A5000000002",
                bronze_ref="bronze.openalex_works_raw:openalex_id=W4400000001",
                full_name="Wei Zhang",
                affiliation_raw="ETH Zürich",
                country_code="CH",
                keywords=("robot-learning",),
                source_url="https://api.openalex.org/people/A5000000002",
            )
        ),
        make_psr(
            PsrSeed(
                source="github",
                source_key="501002",
                bronze_ref="bronze.github_users_raw:user_id=501002",
                full_name="Wei Zhang",
                github_login="weizhang-robotics",
                affiliation_raw="ETH Zürich",
                location_raw="Zurich",
                country_code="CH",
                keywords=("robot-learning", "simulation"),
                bio="Robot learning and simulation.",
                source_url="https://api.github.com/users/weizhang-robotics",
            )
        ),
        make_psr(
            PsrSeed(
                source="openalex_author",
                source_key="A5000000003",
                full_name="Wei Zhang",
                affiliation_raw="National University of Singapore",
                country_code="SG",
                keywords=("databases", "query-optimization"),
                source_url="https://api.openalex.org/people/A5000000003",
            )
        ),
        make_psr(
            PsrSeed(
                source="github",
                source_key="501003",
                bronze_ref="bronze.github_users_raw:user_id=501003",
                full_name="Nils Berger",
                emails=("nils@berger.dev",),
                github_login="nilsberger",
                location_raw="Munich",
                country_code="DE",
                keywords=("simulation",),
                source_url="https://api.github.com/users/nilsberger",
            )
        ),
        make_psr(
            PsrSeed(
                source="arxiv_author",
                source_key=f"{BERGER_ARXIV}:1",
                bronze_ref=f"bronze.arxiv_papers_raw:arxiv_id={BERGER_ARXIV}",
                full_name="Nils Berger",
                emails=("nils@berger.dev",),
                source_url=f"https://arxiv.org/abs/{BERGER_ARXIV}",
            )
        ),
        make_psr(
            PsrSeed(
                source="openalex_author",
                source_key="A5000000005",
                bronze_ref="bronze.openalex_works_raw:openalex_id=W4400000002",
                full_name="A. Patel",
                orcid="0000-0001-5109-3700",
                affiliation_raw="KTH Royal Institute of Technology",
                country_code="SE",
                keywords=("slam",),
                source_url="https://api.openalex.org/people/A5000000005",
            )
        ),
        make_psr(
            PsrSeed(
                source="enrichment",
                source_key="aisha-patel-site",
                full_name="Aisha Patel",
                orcid="0000-0001-5109-3700",
                website_url="https://aishapatel.se",
                source_url="https://aishapatel.se/about",
            )
        ),
        make_psr(
            PsrSeed(
                source="github",
                source_key="501006",
                bronze_ref="bronze.github_users_raw:user_id=501006",
                full_name="Jonas Keller",
                github_login="jonaskeller",
                location_raw="Berlin",
                country_code="DE",
                source_url="https://api.github.com/users/jonaskeller",
            )
        ),
        make_psr(
            PsrSeed(
                source="zefix_officer",
                source_key=f"{KELLER_UID}:keller jonas",
                bronze_ref="bronze.zefix_companies_raw:uid=" + KELLER_UID,
                full_name="Jonas Keller",
                affiliation_raw="Keller Advisory GmbH",
                location_raw="Zug",
                country_code="CH",
                source_url=f"https://www.zefix.admin.ch/api/v1/company/uid/{KELLER_UID}",
            )
        ),
    ]


def _person(person_id: str, full_name: str, **overrides: SinkValue) -> Row:
    row: Row = {
        "person_id": person_id,
        "full_name": full_name,
        "display_name": full_name,
        "primary_email": None,
        "emails": [],
        "github_login": None,
        "orcid": None,
        "website_url": None,
        "linkedin_url": None,
        "cv_url": None,
        "twitter_handle": None,
        "affiliation": None,
        "location": None,
        "country_code": None,
        "headline": None,
        "avatar_url": None,
        "data_quality_score": 0.5,
        "status": "active",
        "merged_into_person_id": None,
        "created_at": T_UPDATED,
        "updated_at": T_UPDATED,
    }
    row.update(overrides)
    return row


def _persons() -> list[Row]:
    return [
        _person(
            LENA,
            "Léna Fischer",
            primary_email="lena.fischer@ethz.ch",
            emails=["lena.fischer@ethz.ch"],
            github_login="lenafischer",
            orcid="0000-0002-1825-0097",
            website_url="https://grasplab.ch",
            # D7 spine: survivorship carries the github-side raw spelling.
            linkedin_url=LENA_LINKEDIN_GITHUB_RAW,
            affiliation="ETH Zürich",
            location="Zurich, Switzerland",
            country_code="CH",
            headline="Robotics founder building grasping foundation models at GraspLab.",
            avatar_url="https://avatars.example.com/u/501001",
            data_quality_score=0.9,
        ),
        _person(
            WEI_A,
            "Wei Zhang",
            github_login="weizhang-robotics",
            affiliation="ETH Zürich",
            # The hacknation identity is Wei's third independent source: the
            # github PSR's location survives and the quality score caps out.
            location="Zurich",
            country_code="CH",
            headline="Robot learning researcher at ETH Zurich.",
            data_quality_score=0.9,
        ),
        _person(
            WEI_B,
            "Wei Zhang",
            affiliation="National University of Singapore",
            country_code="SG",
            headline="Database systems researcher in Singapore.",
            data_quality_score=0.6,
        ),
        _person(
            NILS,
            "Nils Berger",
            primary_email="nils@berger.dev",
            emails=["nils@berger.dev"],
            github_login="nilsberger",
            location="Munich",
            country_code="DE",
            headline="Simulation engineer behind FastSim.",
            data_quality_score=0.7,
        ),
        _person(
            AISHA,
            "Aisha Patel",
            orcid="0000-0001-5109-3700",
            website_url="https://aishapatel.se",
            affiliation="KTH Royal Institute of Technology",
            country_code="SE",
            headline="SLAM researcher at KTH.",
            data_quality_score=0.6,
        ),
        _person(
            JONAS_DEV,
            "Jonas Keller",
            github_login="jonaskeller",
            location="Berlin",
            country_code="DE",
            headline="Software developer in Berlin.",
            data_quality_score=0.5,
        ),
        _person(
            JONAS_LAW,
            "Jonas Keller",
            affiliation="Keller Advisory GmbH",
            location="Zug",
            country_code="CH",
            headline="Corporate advisor in Zug.",
            data_quality_score=0.5,
        ),
        # Survivorship of the merged hacknation PSR: country_code stays None
        # because the payload spells "Sweden", not an ISO code.
        _person(
            SELIN,
            "Selin Aydın",  # noqa: RUF001 - Turkish dotless i is the real spelling
            primary_email="selin.aydin@careloop.se",
            emails=["selin.aydin@careloop.se"],
            linkedin_url="linkedin.com/in/selin-aydin-kth",
            cv_url=SELIN_CV_URL,
            affiliation="KTH Royal Institute of Technology",
            location="Stockholm, Sweden",
            headline="Care coordination copilot for hospitals",
            avatar_url="https://cdn.hack-nation.ai/avatars/hn-selin-0003.png",
            # Single-source person (hacknation only): base quality, no bonus.
            data_quality_score=0.5,
        ),
    ]


def _link(
    person_id: str, source_record_id: str, method: str, confidence: float, evidence: Row
) -> Row:
    """One active ER link row."""
    return {
        "link_id": ids.link_id(person_id, source_record_id, method),
        "person_id": person_id,
        "source_record_id": source_record_id,
        "match_confidence": confidence,
        "match_method": method,
        "evidence": evidence,
        "pipeline_version": PIPELINE_VERSION,
        "matched_at": T_UPDATED,
        "status": "active",
        "retracted_at": None,
        "retracted_by": None,
        "retracted_reason": None,
    }


def _retracted(link: Row, reason: str) -> Row:
    """Mark a link analyst-retracted: the reversible unmerge shape."""
    return {
        **link,
        "status": "retracted",
        "retracted_at": T_UPDATED,
        "retracted_by": "analyst",
        "retracted_reason": reason,
    }


def _links() -> list[Row]:
    return [
        _link(
            LENA,
            PSR_LENA_GITHUB,
            "det_email",
            0.98,
            {"rule": "D2", "email": "lena.fischer@ethz.ch"},
        ),
        _link(
            LENA,
            PSR_LENA_OPENALEX,
            "det_orcid",
            0.99,
            {"rule": "D1", "orcid": "0000-0002-1825-0097"},
        ),
        _link(
            LENA,
            PSR_LENA_ZEFIX,
            "det_crosslink",
            0.92,
            {"rule": "D5", "crosslink": "grasplab.ch == github blog", "name_jw": 0.98},
        ),
        _link(
            WEI_A,
            PSR_WEI_A_OPENALEX,
            "det_crosslink",
            0.92,
            {"rule": "D5", "crosslink": "coauthor on 2506.11111 x contributor", "name_jw": 1.0},
        ),
        _link(
            WEI_A,
            PSR_WEI_A_GITHUB,
            "llm_adjudication",
            0.90,
            {
                "verdict": "match",
                "rationale": "Same org, same robotics focus, login matches name",
                "fields_supporting": ["org_norm", "keywords", "country_code"],
            },
        ),
        _link(WEI_B, PSR_WEI_B_OPENALEX, "seed_fixture", 0.95, {"rule": "fixture seed"}),
        _link(NILS, PSR_NILS_GITHUB, "det_email", 0.98, {"rule": "D2", "email": "nils@berger.dev"}),
        _link(NILS, PSR_NILS_ARXIV, "det_email", 0.98, {"rule": "D2", "email": "nils@berger.dev"}),
        _link(
            AISHA,
            PSR_AISHA_OPENALEX,
            "det_orcid",
            0.99,
            {"rule": "D1", "orcid": "0000-0001-5109-3700"},
        ),
        _link(
            AISHA,
            PSR_AISHA_ENRICHMENT,
            "det_orcid",
            0.99,
            {"rule": "D1", "orcid": "0000-0001-5109-3700"},
        ),
        _link(JONAS_DEV, PSR_JONAS_GITHUB, "seed_fixture", 0.95, {"rule": "fixture seed"}),
        _retracted(
            _link(
                JONAS_DEV,
                PSR_JONAS_ZEFIX,
                "splink",
                0.72,
                {"comparison_vector": {"name": 2, "org": 0, "country": 0}},
            ),
            "Different person: Berlin developer vs Zug advisor",
        ),
        _link(
            JONAS_LAW,
            PSR_JONAS_ZEFIX,
            "human_review",
            0.95,
            {"rule": "unmerge correction", "reviewer_note": "SHAB officer is the Zug advisor"},
        ),
        # Hack Nation links stay appended: tests pin the retracted link's index.
        _link(
            LENA,
            PSR_LENA_HN,
            "det_linkedin",
            0.97,
            {"rule": "D7", "linkedin_url": norm.url_norm(LENA_LINKEDIN_GITHUB_RAW)},
        ),
        _link(
            WEI_A,
            PSR_WEI_HN,
            "det_hn_repo",
            0.90,
            {
                "rule": "D8",
                "repo": "grasplab/grasp-anything",
                "name_jw": 1.0,
                "hn_project_id": HN_P1_ID,
            },
        ),
        _link(SELIN, PSR_SELIN_HN, "seed_fixture", 0.95, {"rule": "fixture seed"}),
    ]


def _silver_artifacts() -> Tables:
    projects: list[Row] = [
        {
            "project_id": GRASP_PROJECT,
            "repo_id": GRASP_REPO_ID,
            "full_name": "grasplab/grasp-anything",
            "name": "grasp-anything",
            "owner_login": "grasplab",
            "is_org_owned": True,
            "description": "Foundation models for robotic grasping",
            "summary_ai": "Open-source grasping foundation models with strong traction.",
            "market_tags": ["robotics", "ai"],
            "usp_notes": "Own grasping foundation model, not a wrapper",
            "primary_language": "Python",
            "languages": {"Python": 182000, "Rust": 21000},
            "topics": ["robotics", "manipulation", "foundation-models"],
            "stars": 8200,
            "forks": 410,
            "license": "Apache-2.0",
            "homepage_url": "https://grasplab.ch",
            "source_platform": "github",
            "github_url": None,
            "structured": None,
            "event_title": None,
            "challenge_title": None,
            "is_winner": None,
            "arxiv_ids_in_readme": [GRASP_ARXIV],
            "funding_signals": [],
            "is_corporate_oss": False,
            "is_academic": False,
            "venture_likeness": 0.92,
            "contributor_count": 2,
            "created_at_source": "2026-03-05T10:00:00+00:00",
            "pushed_at": "2026-07-14T18:22:00+00:00",
            "ai_model_version": "fixture",
            "source_url": "https://github.com/grasplab/grasp-anything",
            "scraped_at": T_SCRAPED,
            "updated_at": T_UPDATED,
        },
        {
            "project_id": FASTSIM_PROJECT,
            "repo_id": FASTSIM_REPO_ID,
            "full_name": "bergerlab/fastsim",
            "name": "fastsim",
            "owner_login": "bergerlab",
            "is_org_owned": False,
            "description": "Differentiable physics simulator",
            "summary_ai": None,
            "market_tags": ["simulation"],
            "usp_notes": None,
            "primary_language": "Python",
            "languages": {"Python": 64000},
            "topics": ["simulation"],
            "stars": 950,
            "forks": 88,
            "license": "MIT",
            "homepage_url": None,
            "source_platform": "github",
            "github_url": None,
            "structured": None,
            "event_title": None,
            "challenge_title": None,
            "is_winner": None,
            "arxiv_ids_in_readme": [BERGER_ARXIV],
            "funding_signals": [],
            "is_corporate_oss": False,
            "is_academic": True,
            "venture_likeness": 0.55,
            "contributor_count": 1,
            "created_at_source": "2026-04-01T10:00:00+00:00",
            "pushed_at": "2026-07-10T11:00:00+00:00",
            "ai_model_version": "fixture",
            "source_url": "https://github.com/bergerlab/fastsim",
            "scraped_at": T_SCRAPED,
            "updated_at": T_UPDATED,
        },
    ]
    noise_projects = [
        (910003, "ml-hub/awesome-robot-learning", "Curated list of robot learning resources", 0.05),
        (910004, "uni-zh/cs-101-exercises", "Course exercises for CS101", 0.08),
        (910005, "someone/dotfiles", "My dotfiles", 0.02),
    ]
    for repo_id, full_name, description, likeness in noise_projects:
        owner, name = full_name.split("/")
        projects.append(
            {
                "project_id": ids.project_id(repo_id),
                "repo_id": repo_id,
                "full_name": full_name,
                "name": name,
                "owner_login": owner,
                "is_org_owned": False,
                "description": description,
                "summary_ai": None,
                "market_tags": [],
                "usp_notes": None,
                "primary_language": None,
                "languages": None,
                "topics": [],
                "stars": 1200,
                "forks": 40,
                "license": None,
                "homepage_url": None,
                "source_platform": "github",
                "github_url": None,
                "structured": None,
                "event_title": None,
                "challenge_title": None,
                "is_winner": None,
                "arxiv_ids_in_readme": [],
                "funding_signals": [],
                "is_corporate_oss": False,
                "is_academic": False,
                "venture_likeness": likeness,
                "contributor_count": 1,
                "created_at_source": "2026-01-01T00:00:00+00:00",
                "pushed_at": "2026-07-01T00:00:00+00:00",
                "ai_model_version": "fixture",
                "source_url": f"https://github.com/{full_name}",
                "scraped_at": T_SCRAPED,
                "updated_at": T_UPDATED,
            }
        )
    # Hack Nation rows come from the real WS-G silver builder, not literals.
    projects.extend(
        hacknation_project_row(
            payload(),
            source_url=f"{HN_PROJECT_URL_PREFIX}{project_key}",
            scraped_at=T_SCRAPED_DT,
            updated_at=T_UPDATED_DT,
        )
        for project_key, payload in (
            (HN_P1_ID, _hn_graspos_payload),
            (HN_P2_ID, _hn_careloop_payload),
        )
    )
    publications: list[Row] = [
        {
            "publication_id": GRASP_PUBLICATION,
            "doi": None,
            "arxiv_id": GRASP_ARXIV,
            "openalex_id": "W4400000001",
            "s2_id": None,
            "title": "GraspFM: Foundation Models for Robotic Grasping",
            "abstract": "We present GraspFM, a family of foundation models for grasping.",
            "published_at": "2026-06-10",
            "venue": "arXiv",
            "primary_source": "arxiv",
            "sources": ["arxiv", "openalex"],
            "concepts": ["robotics", "manipulation"],
            "code_urls": ["https://github.com/grasplab/grasp-anything"],
            "citation_count": 41,
            "is_preprint": True,
            "source_extras": {"arxiv_comment": "Project page: https://grasplab.ch"},
            "source_url": f"https://arxiv.org/abs/{GRASP_ARXIV}",
            "scraped_at": T_SCRAPED,
            "updated_at": T_UPDATED,
        },
        {
            "publication_id": BERGER_PUBLICATION,
            "doi": None,
            "arxiv_id": BERGER_ARXIV,
            "openalex_id": None,
            "s2_id": None,
            "title": "FastSim: Differentiable Contact Simulation",
            "abstract": "A differentiable physics simulator for contact-rich tasks.",
            "published_at": "2026-07-01",
            "venue": "arXiv",
            "primary_source": "arxiv",
            "sources": ["arxiv"],
            "concepts": ["simulation"],
            "code_urls": ["https://github.com/bergerlab/fastsim"],
            "citation_count": 3,
            "is_preprint": True,
            "source_extras": None,
            "source_url": f"https://arxiv.org/abs/{BERGER_ARXIV}",
            "scraped_at": T_SCRAPED,
            "updated_at": T_UPDATED,
        },
        {
            "publication_id": SLAM_PUBLICATION,
            "doi": "10.1234/slam.2026.777",
            "arxiv_id": None,
            "openalex_id": "W4400000002",
            "s2_id": None,
            "title": "Sparse Maps for Lifelong SLAM",
            "abstract": "Sparse map maintenance for lifelong SLAM.",
            "published_at": "2026-05-20",
            "venue": "ICRA",
            "primary_source": "openalex",
            "sources": ["openalex"],
            "concepts": ["slam"],
            "code_urls": [],
            "citation_count": 12,
            "is_preprint": False,
            "source_extras": None,
            "source_url": "https://api.openalex.org/works/W4400000002",
            "scraped_at": T_SCRAPED,
            "updated_at": T_UPDATED,
        },
    ]
    companies: list[Row] = [
        {
            "company_id": GRASP_COMPANY,
            "uid": GRASP_UID,
            "name": "GraspLab AG",
            "legal_form": "AG",
            "legal_seat": "Zürich",
            "canton": "ZH",
            "address_street": "Technoparkstrasse 1",
            "address_zip": "8005",
            "address_town": "Zürich",
            "purpose": "Entwicklung und Vertrieb von Software für Robotergreifsysteme",
            "startup_likeness": "tech_startup_candidate",
            "status": "ACTIVE",
            "incorporation_date": "2026-06-20",
            "website_url": "https://grasplab.ch",
            "first_sogc_id": "SHAB-2026-001234",
            "source_url": f"https://www.zefix.admin.ch/api/v1/company/uid/{GRASP_UID}",
            "scraped_at": T_SCRAPED,
            "updated_at": T_UPDATED,
        },
        {
            "company_id": KELLER_COMPANY,
            "uid": KELLER_UID,
            "name": "Keller Advisory GmbH",
            "legal_form": "GmbH",
            "legal_seat": "Zug",
            "canton": "ZG",
            "address_street": "Bahnhofstrasse 2",
            "address_zip": "6300",
            "address_town": "Zug",
            "purpose": "Beratung und Verwaltung von Beteiligungen",
            "startup_likeness": "traditional",
            "status": "ACTIVE",
            "incorporation_date": "2024-02-01",
            "website_url": None,
            "first_sogc_id": None,
            "source_url": f"https://www.zefix.admin.ch/api/v1/company/uid/{KELLER_UID}",
            "scraped_at": T_SCRAPED,
            "updated_at": T_UPDATED,
        },
    ]
    return {
        "silver.project": projects,
        "silver.publication": publications,
        "silver.company": companies,
    }


def _silver_facts() -> Tables:
    contributions: list[Row] = [
        {
            "contribution_id": ids.contribution_id(GRASP_PROJECT, PSR_LENA_GITHUB),
            "project_id": GRASP_PROJECT,
            "source_record_id": PSR_LENA_GITHUB,
            "person_id": LENA,
            "commit_count": 342,
            "additions": 51000,
            "deletions": 9000,
            "sample_commit_shas": ["c0ffee0000000000000000000000000000000001"],
            "commit_emails": ["lena.fischer@ethz.ch"],
            "languages": ["Python", "Rust"],
            "first_commit_at": "2026-03-05T11:00:00+00:00",
            "last_commit_at": "2026-07-14T18:00:00+00:00",
            "contribution_share": 0.62,
            "confidence": 0.95,
            "corroboration_count": 2,
            "is_provisional": False,
            "computed_at": T_UPDATED,
            "source_url": "https://github.com/grasplab/grasp-anything/commits?author=lenafischer",
        },
        {
            "contribution_id": ids.contribution_id(GRASP_PROJECT, PSR_WEI_A_GITHUB),
            "project_id": GRASP_PROJECT,
            "source_record_id": PSR_WEI_A_GITHUB,
            "person_id": WEI_A,
            "commit_count": 208,
            "additions": 30000,
            "deletions": 5000,
            "sample_commit_shas": [],
            "commit_emails": [],
            "languages": ["Python"],
            "first_commit_at": "2026-03-10T11:00:00+00:00",
            "last_commit_at": "2026-07-13T18:00:00+00:00",
            "contribution_share": 0.38,
            "confidence": 0.9,
            "corroboration_count": 2,
            "is_provisional": False,
            "computed_at": T_UPDATED,
            "source_url": "https://github.com/grasplab/grasp-anything/commits?author=weizhang-robotics",
        },
        {
            "contribution_id": ids.contribution_id(FASTSIM_PROJECT, PSR_NILS_GITHUB),
            "project_id": FASTSIM_PROJECT,
            "source_record_id": PSR_NILS_GITHUB,
            "person_id": NILS,
            "commit_count": 121,
            "additions": 20000,
            "deletions": 4000,
            "sample_commit_shas": ["c0ffee0000000000000000000000000000000002"],
            "commit_emails": ["nils@berger.dev"],
            "languages": ["Python"],
            "first_commit_at": "2026-04-01T11:00:00+00:00",
            "last_commit_at": "2026-07-10T10:30:00+00:00",
            "contribution_share": 1.0,
            "confidence": 0.9,
            "corroboration_count": 1,
            "is_provisional": True,
            "computed_at": T_UPDATED,
            "source_url": "https://github.com/bergerlab/fastsim/commits?author=nilsberger",
        },
    ]
    authorships: list[Row] = [
        {
            "authorship_id": ids.authorship_id(GRASP_PUBLICATION, PSR_LENA_OPENALEX),
            "publication_id": GRASP_PUBLICATION,
            "source_record_id": PSR_LENA_OPENALEX,
            "person_id": LENA,
            "author_position": 1,
            "is_last_author": False,
            "raw_author_name": "Léna Fischer",
            "affiliation_raw": "ETH Zürich",
            "confidence": 0.95,
            "corroboration_count": 2,
            "is_provisional": False,
            "source_url": "https://api.openalex.org/works/W4400000001",
            "updated_at": T_UPDATED,
        },
        {
            "authorship_id": ids.authorship_id(GRASP_PUBLICATION, PSR_WEI_A_OPENALEX),
            "publication_id": GRASP_PUBLICATION,
            "source_record_id": PSR_WEI_A_OPENALEX,
            "person_id": WEI_A,
            "author_position": 2,
            "is_last_author": True,
            "raw_author_name": "Wei Zhang",
            "affiliation_raw": "ETH Zürich",
            "confidence": 0.9,
            "corroboration_count": 2,
            "is_provisional": False,
            "source_url": "https://api.openalex.org/works/W4400000001",
            "updated_at": T_UPDATED,
        },
        {
            "authorship_id": ids.authorship_id(BERGER_PUBLICATION, PSR_NILS_ARXIV),
            "publication_id": BERGER_PUBLICATION,
            "source_record_id": PSR_NILS_ARXIV,
            "person_id": NILS,
            "author_position": 1,
            "is_last_author": True,
            "raw_author_name": "Nils Berger",
            "affiliation_raw": None,
            "confidence": 0.85,
            "corroboration_count": 1,
            "is_provisional": True,
            "source_url": f"https://arxiv.org/abs/{BERGER_ARXIV}",
            "updated_at": T_UPDATED,
        },
        {
            "authorship_id": ids.authorship_id(SLAM_PUBLICATION, PSR_AISHA_OPENALEX),
            "publication_id": SLAM_PUBLICATION,
            "source_record_id": PSR_AISHA_OPENALEX,
            "person_id": AISHA,
            "author_position": 1,
            "is_last_author": True,
            "raw_author_name": "A. Patel",
            "affiliation_raw": "KTH Royal Institute of Technology",
            "confidence": 0.9,
            "corroboration_count": 1,
            "is_provisional": True,
            "source_url": "https://api.openalex.org/works/W4400000002",
            "updated_at": T_UPDATED,
        },
    ]
    officers: list[Row] = [
        {
            "officer_id": ids.officer_id(GRASP_COMPANY, PSR_LENA_ZEFIX, "founder"),
            "company_id": GRASP_COMPANY,
            "source_record_id": PSR_LENA_ZEFIX,
            "person_id": LENA,
            "role": "Mitglied des Verwaltungsrates",
            "role_norm": "founder",
            "signing_authority": "Einzelunterschrift",
            "registered_at": "2026-06-20",
            "deregistered_at": None,
            "evidence_sogc_id": "SHAB-2026-001234",
            "confidence": 0.92,
            "corroboration_count": 2,
            "is_provisional": False,
            "source_url": "https://amtsblattportal.ch/api/v1/publications/SHAB-2026-001234",
            "updated_at": T_UPDATED,
        },
        {
            "officer_id": ids.officer_id(KELLER_COMPANY, PSR_JONAS_ZEFIX, "md"),
            "company_id": KELLER_COMPANY,
            "source_record_id": PSR_JONAS_ZEFIX,
            "person_id": JONAS_LAW,
            "role": "Geschäftsführer",
            "role_norm": "md",
            "signing_authority": "Einzelunterschrift",
            "registered_at": "2024-02-01",
            "deregistered_at": None,
            "evidence_sogc_id": None,
            "confidence": 0.95,
            "corroboration_count": 1,
            "is_provisional": True,
            "source_url": f"https://www.zefix.admin.ch/api/v1/company/uid/{KELLER_UID}",
            "updated_at": T_UPDATED,
        },
    ]
    connections: list[Row] = [
        {
            "person_a_id": LENA,
            "person_b_id": WEI_A,
            "connection_type": "coauthor",
            "weight": 1.0,
            "evidence": [GRASP_PUBLICATION],
            "first_seen": "2026-06-10",
            "last_seen": "2026-06-10",
            "updated_at": T_UPDATED,
        },
        {
            "person_a_id": LENA,
            "person_b_id": WEI_A,
            "connection_type": "co_contributor",
            "weight": 1.0,
            "evidence": [GRASP_PROJECT],
            "first_seen": "2026-03-10",
            "last_seen": "2026-07-14",
            "updated_at": T_UPDATED,
        },
    ]
    return {
        "silver.contribution": contributions,
        "silver.authorship": authorships,
        "silver.officer": officers,
        "silver.person_connection": connections,
    }


def _category(score: float | None, method: str, rationale: str, url: str) -> Row:
    """One schema-valid breakdown category with a single cited evidence item."""
    return {
        "score": score,
        "method": method,
        "rationale": rationale,
        "confidence": 0.8,
        "evidence": [{"claim": rationale, "source_url": url, "source_type": "fixture"}],
    }


def _breakdown() -> Row:
    return {
        "schema_version": 1,
        "categories": {
            "individual_experience": _category(
                82.0,
                "sql_features",
                "342 commits in 12mo on an 8,200-star repo",
                "https://github.com/grasplab/grasp-anything",
            ),
            "schools": _category(
                92.0,
                "deterministic",
                "Max tier ETH Zurich (97) across known members",
                "https://api.openalex.org/works/W4400000001",
            ),
            "network_ties": _category(
                60.0,
                "graph",
                "2-hop path to a funded founder via coauthor graph",
                "https://api.openalex.org/works/W4400000001",
            ),
            "prior_collaboration": _category(
                90.0,
                "sql_overlap",
                "Fischer and Zhang share a paper and a repo across 4 months",
                "https://github.com/grasplab/grasp-anything",
            ),
            "problem_realness": _category(
                74.0,
                "web_agent",
                "Recurring complaints about grasping reliability in warehouse automation",
                "https://news.ycombinator.com/item?id=fixture",
            ),
            "product_defensibility": _category(
                80.0,
                "ai_query",
                "Own foundation model, hard-tech stack, permissive license",
                "https://github.com/grasplab/grasp-anything",
            ),
            "market": _category(
                68.0,
                "web_agent",
                "Robotic manipulation TAM growing with named competitors",
                "https://example.com/market-report",
            ),
            "traction": _category(
                71.0,
                "hybrid",
                "8,200 stars in 4 months; revenue unknown pending interview",
                "https://github.com/grasplab/grasp-anything",
            ),
            "ideal_match": _category(
                84.0,
                "structured_match",
                "Education 92, domain-fit 0.91, stars p95",
                "https://grasplab.ch",
            ),
        },
    }


def _hacknation_breakdown() -> Row:
    """CareLoop's breakdown: same schema, evidence cites the showcase payload."""
    url = f"{HN_PROJECT_URL_PREFIX}{HN_P2_ID}"
    seeds: list[tuple[str, float, str]] = [
        ("individual_experience", 64.0, "MSc founder who shipped a working hackathon copilot"),
        ("schools", 82.0, "KTH Royal Institute of Technology, tier 82"),
        ("network_ties", 40.0, "No funded-founder path in the fixture graph"),
        ("prior_collaboration", 55.0, "Solo builder; no repeated collaborators yet"),
        ("problem_realness", 78.0, "Discharge planning still runs on phone and fax"),
        ("product_defensibility", 58.0, "EHR-export integrations around an LLM planning core"),
        ("market", 66.0, "Hospital care-coordination spend is large and underserved"),
        ("traction", 45.0, "Healthcare Challenge finalist; no pilots yet"),
        ("ideal_match", 52.0, "Health copilot against a robotics-focused ideal profile"),
    ]
    categories: Row = {
        name: _category(score, "fixture", rationale, url) for name, score, rationale in seeds
    }
    return {"schema_version": 1, "categories": categories}


def _memo_sections() -> Row:
    def cited(text: str, url: str) -> Row:
        return {
            "text": text,
            "evidence": [{"claim": text, "source_url": url, "source_type": "fixture"}],
        }

    def missing(text: str, gap_field: str) -> Row:
        return {"text": text, "missing": True, "gap_field": gap_field}

    return {
        "schema_version": 1,
        "company_snapshot": {
            "bullets": [
                cited(
                    "GraspLab AG incorporated in Zurich on 2026-06-20.",
                    "https://www.zefix.admin.ch/api/v1/company/uid/CHE-123.456.789",
                )
            ]
        },
        "investment_hypotheses": {
            "bullets": [
                cited(
                    "Grasping foundation models are becoming the default robotics stack.",
                    "https://arxiv.org/abs/2506.11111",
                )
            ]
        },
        "swot": {
            "bullets": [
                cited(
                    "Strength: 8,200-star open-source traction in 4 months.",
                    "https://github.com/grasplab/grasp-anything",
                )
            ]
        },
        "team_and_history": {
            "bullets": [
                cited(
                    "Founder Lena Fischer links GitHub, arXiv, and the Zefix registry.",
                    "https://api.openalex.org/works/W4400000001",
                )
            ]
        },
        "problem_and_product": {
            "bullets": [
                cited(
                    "GraspFM targets unreliable grasping in warehouse automation.",
                    "https://arxiv.org/abs/2506.11111",
                )
            ]
        },
        "technology_and_defensibility": {
            "bullets": [
                cited(
                    "Own foundation model with published research, not an API wrapper.",
                    "https://arxiv.org/abs/2506.11111",
                )
            ]
        },
        "market_tam_sam_som": {
            "bullets": [missing("Bottom-up market sizing not yet computed.", "market.tam")],
            "tam": None,
            "sam": None,
            "som": None,
            "assumptions": [],
        },
        "competition": {
            "bullets": [
                cited(
                    "Competes with in-house grasping stacks at large robotics vendors.",
                    "https://example.com/market-report",
                )
            ]
        },
        "traction_and_kpis": {
            "bullets": [
                cited(
                    "8,200 GitHub stars, 410 forks.", "https://github.com/grasplab/grasp-anything"
                ),
                missing("Revenue and pilot count unknown.", "traction.revenue"),
            ]
        },
    }


def _gold() -> Tables:
    venture: Row = {
        "venture_id": GRASP_VENTURE,
        "anchor_type": "repo",
        "anchor_id": GRASP_PROJECT,
        "name": "GraspLab",
        "one_liner": "Foundation models for robotic grasping",
        "summary_ai": "ETH spin-off shipping open-source grasping foundation models.",
        "market_tags": ["robotics", "ai"],
        "website_url": "https://grasplab.ch",
        "quality_tier": "scored",
        "status": "interviewing",
        "created_at": T_UPDATED,
        "updated_at": T_UPDATED,
    }
    # GraspOS Studio (P1) pitches the grasp-anything repo, so it merges into the
    # existing repo-anchored venture instead of minting a hackathon twin;
    # repo-less CareLoop (P2) is the one hackathon_project-anchored venture.
    careloop: Row = {
        "venture_id": SELIN_VENTURE,
        "anchor_type": "hackathon_project",
        "anchor_id": HN_P2_PROJECT,
        "name": "CareLoop",
        "one_liner": "Care-coordination copilot for hospital discharge planning",
        "summary_ai": "Hackathon-born hospital discharge copilot by a KTH founder.",
        "market_tags": ["health", "ai"],
        "website_url": None,
        "quality_tier": "scored",
        "status": "scored",
        "created_at": T_UPDATED,
        "updated_at": T_UPDATED,
    }
    members: list[Row] = [
        {
            "venture_id": GRASP_VENTURE,
            "person_id": LENA,
            "role_hint": "founder",
            "is_founder_guess": True,
            "weight": 0.62,
            "evidence": {
                "contribution_share": 0.62,
                "officer_role": "founder",
                "hacknation_author": HN_P1_ID,
            },
            "added_by": "pipeline",
            "added_at": T_UPDATED,
        },
        {
            "venture_id": GRASP_VENTURE,
            "person_id": WEI_A,
            "role_hint": "maintainer",
            "is_founder_guess": False,
            "weight": 0.38,
            "evidence": {"contribution_share": 0.38, "hacknation_role": "ML Engineer"},
            "added_by": "pipeline",
            "added_at": T_UPDATED,
        },
        {
            "venture_id": SELIN_VENTURE,
            "person_id": SELIN,
            "role_hint": "founder",
            "is_founder_guess": True,
            "weight": 1.0,
            "evidence": {"source": "hacknation", "role": "author"},
            "added_by": "pipeline",
            "added_at": T_UPDATED,
        },
    ]
    thesis: Row = {
        "thesis_id": THESIS_ID,
        "name": "Swiss deep-tech pre-seed",
        "owner_email": "partner@fund.example",
        "sectors": ["robotics", "ai"],
        "geographies": ["CH", "EU"],
        "stages": ["pre-seed", "seed"],
        "check_size_min_chf": 250000,
        "check_size_max_chf": 1000000,
        "require_no_prior_vc": True,
        "min_team": 1,
        "max_team": 6,
        "exclude_corporate_oss": True,
        "notes": "Hardware-adjacent AI, researcher founders.",
        "is_active": True,
        "updated_by": "partner@fund.example",
        "updated_at": T_UPDATED,
    }
    weights: Row = {
        "weights_id": WEIGHTS_ID,
        "thesis_id": THESIS_ID,
        "version": 1,
        "w_individual_experience": 0.15,
        "w_schools": 0.10,
        "w_network_ties": 0.05,
        "w_prior_collaboration": 0.10,
        "w_problem_realness": 0.15,
        "w_product_defensibility": 0.15,
        "w_market": 0.10,
        "w_traction": 0.10,
        "w_ideal_match": 0.10,
        "is_active": True,
        "updated_by": "partner@fund.example",
        "updated_at": T_UPDATED,
    }
    ideal: Row = {
        "profile_id": IDEAL_ID,
        "thesis_id": THESIS_ID,
        "version": 1,
        "profile_json": {
            "schema_version": 1,
            "narrative": "Robotics researcher-founder shipping open-source manipulation stacks.",
            "education": [{"institution": "ETH Zurich", "level": "phd", "field": "robotics"}],
            "sectors": ["robotics"],
            "keywords": ["manipulation", "grasping", "foundation models"],
            "numeric_features": {"school_tier": 0.95, "stars_weighted": 0.8, "recency_score": 0.9},
            "feature_weights": {"school_tier": 1.0, "stars_weighted": 1.0, "recency_score": 0.5},
        },
        "profile_text": IDEAL_TEXT,
        "embedding": _embedding(IDEAL_TEXT),
        "embedding_model": "fixture-fake-embedding",
        "is_active": True,
        "updated_by": "partner@fund.example",
        "updated_at": T_UPDATED,
    }
    pool: Row = {
        "thesis_id": THESIS_ID,
        "venture_id": GRASP_VENTURE,
        "included": True,
        "exclusion_reasons": [],
        "funding_signal": "none_found",
        "pool_built_at": T_UPDATED,
    }
    hn_pool: Row = {
        "thesis_id": THESIS_ID,
        "venture_id": SELIN_VENTURE,
        "included": True,
        "exclusion_reasons": [],
        "funding_signal": "none_found",
        "pool_built_at": T_UPDATED,
    }
    score_common: Row = {
        "venture_id": GRASP_VENTURE,
        "thesis_id": THESIS_ID,
        "weights_id": WEIGHTS_ID,
        "profile_id": IDEAL_ID,
        "model_version": "fixture-scorer-1",
        "s_individual_experience": 82.0,
        "s_schools": 92.0,
        "s_network_ties": 60.0,
        "s_prior_collaboration": 90.0,
        "s_problem_realness": 74.0,
        "s_product_defensibility": 80.0,
        "s_market": 68.0,
        "s_traction": 71.0,
        "ideal_match": 84.0,
        "breakdown": _breakdown(),
    }
    scores: list[Row] = [
        {
            "score_id": SCORE_LATEST_ID,
            **score_common,
            "scored_at": T_UPDATED,
            "final_score": 78.4,
            "confidence": 0.82,
            "is_latest": True,
        },
        {
            "score_id": SCORE_OLD_ID,
            **score_common,
            "scored_at": T_OLD_SCORE,
            "final_score": 74.1,
            "confidence": 0.7,
            "is_latest": False,
        },
        {
            "score_id": SCORE_CARELOOP_ID,
            "venture_id": SELIN_VENTURE,
            "thesis_id": THESIS_ID,
            "weights_id": WEIGHTS_ID,
            "profile_id": IDEAL_ID,
            "model_version": "fixture-scorer-1",
            "s_individual_experience": 64.0,
            "s_schools": 82.0,
            "s_network_ties": 40.0,
            "s_prior_collaboration": 55.0,
            "s_problem_realness": 78.0,
            "s_product_defensibility": 58.0,
            "s_market": 66.0,
            "s_traction": 45.0,
            "ideal_match": 52.0,
            "breakdown": _hacknation_breakdown(),
            "scored_at": T_UPDATED,
            "final_score": 62.0,
            "confidence": 0.6,
            "is_latest": True,
        },
    ]
    features: list[Row] = [
        {
            "person_id": LENA,
            "features": {
                "stars_weighted": 8.53,
                "commits_12mo": 342.0,
                "school_tier": 0.97,
                "recency_score": 0.95,
                "zero_to_one_flag": 1.0,
            },
            "profile_text": LENA_TEXT,
            "profile_embedding": _embedding(LENA_TEXT),
            "embedding_model": "fixture-fake-embedding",
            "computed_at": T_UPDATED,
        },
        {
            "person_id": WEI_A,
            "features": {
                "stars_weighted": 7.9,
                "commits_12mo": 208.0,
                "school_tier": 0.97,
                "recency_score": 0.9,
            },
            "profile_text": WEI_A_TEXT,
            "profile_embedding": _embedding(WEI_A_TEXT),
            "embedding_model": "fixture-fake-embedding",
            "computed_at": T_UPDATED,
        },
    ]
    gaps: list[Row] = [
        {
            "venture_id": GRASP_VENTURE,
            "field": "traction.revenue",
            "category": "traction",
            "question_text": "Do you have paying pilots or revenue today?",
            "importance": 0.9,
            "created_at": T_UPDATED,
        },
        {
            "venture_id": GRASP_VENTURE,
            "field": "market.tam",
            "category": "market",
            "question_text": "Which customer segment do you serve first, and how large is it?",
            "importance": 0.7,
            "created_at": T_UPDATED,
        },
    ]
    memo: Row = {
        "memo_id": MEMO_ID,
        "venture_id": GRASP_VENTURE,
        "thesis_id": THESIS_ID,
        "run_id": RUN_ID,
        "sections": _memo_sections(),
        "model_version": "fixture-memo-1",
        "generated_at": T_UPDATED,
        "status": "draft",
        "is_latest": True,
    }
    outreach: Row = {
        "outreach_id": OUTREACH_ID,
        "venture_id": GRASP_VENTURE,
        "thesis_id": THESIS_ID,
        "person_id": LENA,
        "channel": "email",
        "to_email": "lena.fischer@ethz.ch",
        "subject": "Your work on GraspFM",
        "body": "We came across your repository grasp-anything and your paper GraspFM...",
        "token_hash": "5df6e0e2761359d30a8275058e299fcc0381534545f55cf43e41983f5d4c9456",
        "token_expires_at": "2026-07-29T09:00:00+00:00",
        "question_plan": {"questions": ["Do you have paying pilots or revenue today?"]},
        "status": "consented",
        "consent_at": "2026-07-16T10:00:00+00:00",
        "sent_at": "2026-07-15T10:00:00+00:00",
        "last_event_at": "2026-07-16T10:00:00+00:00",
        "history": None,
        "created_by": "partner@fund.example",
        "updated_at": T_UPDATED,
    }
    interview: Row = {
        "interview_id": INTERVIEW_ID,
        "outreach_id": OUTREACH_ID,
        "venture_id": GRASP_VENTURE,
        "person_id": LENA,
        "consent_confirmed": True,
        "started_at": "2026-07-16T10:05:00+00:00",
        "completed_at": "2026-07-16T10:19:00+00:00",
        "transcript": [
            {
                "role": "assistant",
                "text": "Thanks for consenting. Do you have paying pilots?",
                "at": "2026-07-16T10:06:00+00:00",
            },
            {
                "role": "founder",
                "text": "Three paid pilots with logistics companies.",
                "at": "2026-07-16T10:07:00+00:00",
            },
        ],
        "extracted": {
            "schema_version": 1,
            "education": [{"institution": "ETH Zurich", "degree": "PhD", "field": "Robotics"}],
            "career": [{"organization": "GraspLab AG", "role": "Founder", "start_year": 2026}],
            "team_commitment": {"status": "full_time"},
            "traction_claims": [
                {"metric": "paid_pilots", "value": "3", "as_of": "2026-07-16", "verified": False}
            ],
            "funding_status": {"raised_before": False},
        },
        "model_version": "fixture-interview-1",
        "rescore_score_id": SCORE_LATEST_ID,
        "updated_at": T_UPDATED,
    }
    return {
        "gold.venture": [venture, careloop],
        "gold.venture_member": members,
        "gold.thesis": [thesis],
        "gold.score_weights": [weights],
        "gold.ideal_candidate": [ideal],
        "gold.candidate_pool": [pool, hn_pool],
        "gold.venture_score": scores,
        "gold.person_features": features,
        "gold.venture_gaps": gaps,
        "gold.memo": [memo],
        "gold.outreach": [outreach],
        "gold.interview": [interview],
    }


def _resolved_university(query: str) -> InstitutionRecord:
    record = institutions.resolve(query)
    if record is None:
        raise MissingInstitutionError(query)
    return record


def _institution_scores() -> list[Row]:
    # ROR ids, canonical names, and aliases come from the resolver seed;
    # only the calibration numbers are fixture-owned.
    universities = [
        ("Massachusetts Institute of Technology", 1.00, 1.00, 100.0),
        ("ETH Zurich", 0.95, 0.99, 97.0),
        ("Stanford University", 1.00, 1.00, 100.0),
        ("EPFL", 0.90, 0.96, 93.0),
        ("KTH", 0.82, 0.82, 82.0),
        ("University of Zurich", 0.75, 0.75, 75.0),
    ]
    companies = [
        ("GOOGLE", 0.98, 0.98, 98.0),
        ("ANTHROPIC", 0.97, 0.95, 96.0),
        ("KLARNA", 0.80, 0.90, 85.0),
        ("ABB", 0.55, 0.45, 50.0),
    ]
    rows: list[Row] = []
    for query, prestige, outcome, score in universities:
        record = _resolved_university(query)
        alias_keys = sorted({norm.org_key(a) for a in (record.name, *record.aliases)} - {""})
        aliases: list[SinkValue] = list(alias_keys)
        rows.append(
            {
                "institution_id": ids.institution_id(record.ror_id),
                "kind": "university",
                "canonical_name": record.name,
                "aliases": aliases,
                "ror_id": record.ror_id,
                "prestige": prestige,
                "outcome": outcome,
                "score": score,
                "provenance": {
                    "seed": "ws0-fixture",
                    "sources": ["ror-cc0", "leiden-open-cc0", "hand-curated"],
                },
                "updated_at": T_UPDATED,
            }
        )
    for name, prestige, outcome, score in companies:
        rows.append(
            {
                "institution_id": ids.institution_id(name),
                "kind": "company",
                "canonical_name": name,
                "aliases": [norm.org_key(name)],
                "ror_id": None,
                "prestige": prestige,
                "outcome": outcome,
                "score": score,
                "provenance": {"seed": "ws0-fixture", "sources": ["hand-curated"]},
                "updated_at": T_UPDATED,
            }
        )
    return rows


def _ops() -> Tables:
    scrape_state: list[Row] = [
        {
            "source": source,
            "cursor": {"window_end": "2026-07-15"},
            "last_run_at": T_SCRAPED,
            "last_status": "ok",
            "last_error": None,
            "items_upserted": count,
            "updated_at": T_INGESTED,
        }
        for source, count in (("github", 7), ("papers", 4), ("zefix", 3), ("hacknation", 6))
    ]
    review_queue: list[Row] = [
        {
            "review_id": REVIEW_ID,
            "source_record_id": PSR_WEI_B_OPENALEX,
            "candidate_person_id": WEI_A,
            "score": 0.55,
            "method": "splink",
            "features": {"name_norm": "exact", "org_norm": "mismatch", "country_code": "mismatch"},
            "status": "pending",
            "decided_by": None,
            "decided_at": None,
            "created_at": T_UPDATED,
        }
    ]
    suppression: list[Row] = [
        {
            "source": "github",
            "source_key_hash": SUPPRESSED_KEY_HASH,
            "created_at": T_UPDATED,
        },
        {
            "source": "hacknation",
            "source_key_hash": HN_SUPPRESSED_KEY_HASH,
            "created_at": T_UPDATED,
        },
    ]
    return {
        "ops.scrape_state": scrape_state,
        "ops.er_review_queue": review_queue,
        "ops.erasure_suppression": suppression,
    }


def build_tables() -> Tables:
    """Assemble every fixture table.

    Returns:
        Mapping of schema-qualified table name to its rows.
    """
    tables: Tables = {}
    # HN bronze is built once and replayed through the real normalizer, so the
    # fixture PSRs are the normalizer's own output (checklist HN5).
    hacknation_bronze = _hacknation_bronze()
    for part in (
        _github_bronze(),
        _papers_bronze(),
        _zefix_bronze(),
        hacknation_bronze,
        {"silver.person": _persons()},
        {
            "silver.person_source_record": [
                *_person_source_records(),
                *_hacknation_psrs(hacknation_bronze),
            ]
        },
        {"silver.person_source_link": _links()},
        _silver_artifacts(),
        _silver_facts(),
        _gold(),
        {"gold.institution_score": _institution_scores()},
        _ops(),
    ):
        tables.update(part)
    return tables


def _temporal_default(value: object) -> str:
    """json.dumps hook: rows built via the contract dataclass carry real temporals."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(str(type(value)))


def write_jsonl(data_dir: Path = DATA_DIR) -> list[Path]:
    """Write one JSONL file per table.

    Args:
        data_dir: Output directory (fixtures/data by default).

    Returns:
        The written file paths, sorted.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table, rows in sorted(build_tables().items()):
        path = data_dir / f"{table}.jsonl"
        lines = [
            json.dumps(row, ensure_ascii=False, sort_keys=True, default=_temporal_default)
            for row in rows
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    import sys

    for written_path in write_jsonl():
        sys.stdout.write(f"{written_path.name}\n")
