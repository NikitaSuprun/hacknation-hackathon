# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""HN2: the SourceNormalizer seam and the hacknation PSR derivations."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Final

from contracts.interfaces import SourceNormalizer
from contracts.models import BronzeRecord, Json
from er.normalize import hacknation_psrs
from fixtures import build as fx
from scrapers.common.jsonutil import as_mapping, as_sink
from sources.hacknation.ingest import PEOPLE_TABLE, PROJECTS_TABLE
from sources.hacknation.normalize import HacknationNormalizer

DATA_DIR: Final[Path] = Path(__file__).resolve().parents[2] / "fixtures" / "data"

Row = dict[str, Json]


def _rows(table: str) -> list[Row]:
    lines = (DATA_DIR / f"{table}.jsonl").read_text(encoding="utf-8").splitlines()
    return [as_mapping(json.loads(line)) for line in lines if line]


def _people() -> list[Row]:
    return _rows(PEOPLE_TABLE)


def _projects() -> list[Row]:
    return _rows(PROJECTS_TABLE)


def _temporal(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(str(type(value)))


def test_bronze_extractor_reproduces_fixture_psr_bytes() -> None:
    expected = {
        str(row["source_record_id"]): row
        for row in _rows("silver.person_source_record")
        if row["source"] == "hacknation"
    }
    produced = hacknation_psrs(_people(), _projects())
    assert {record.source_record_id for record in produced} == set(expected)
    for record in produced:
        rendered = json.loads(
            json.dumps(record.to_row(), ensure_ascii=False, sort_keys=True, default=_temporal)
        )
        assert rendered == expected[record.source_record_id], record.source_key


def test_keywords_join_field_of_study_tech_stack_and_tags() -> None:
    by_key = {record.source_key: record for record in hacknation_psrs(_people(), _projects())}
    assert by_key[fx.HN_LENA_KEY].keywords == ("ai", "pytorch", "robotics", "ros")
    assert by_key[fx.HN_MIRA_KEY].keywords == (
        "ai",
        "machine learning",
        "python",
        "voice",
        "whisper",
    )


def test_project_side_linkedin_enriches_the_people_row() -> None:
    by_key = {record.source_key: record for record in hacknation_psrs(_people(), _projects())}
    assert by_key[fx.HN_MIRA_KEY].linkedin_url == fx.MIRA_LINKEDIN_HACKNATION
    assert by_key[fx.HN_LENA_KEY].linkedin_url is None


def test_location_and_org_normalize_through_the_shared_tools() -> None:
    by_key = {record.source_key: record for record in hacknation_psrs(_people(), _projects())}
    lena = by_key[fx.HN_LENA_KEY]
    assert lena.location_raw == "Zurich, Switzerland"
    assert lena.country_code == "CH"
    assert lena.affiliation_raw == "ETH Zürich"
    assert lena.org_norm is not None


def test_team_member_missing_from_people_list_still_yields_a_psr() -> None:
    records = hacknation_psrs([], _projects())
    by_key = {record.source_key: record for record in records}
    mira = by_key[fx.HN_MIRA_KEY]
    assert mira.full_name == "Mira Kovac"
    assert mira.bronze_ref == f"bronze.hacknation_projects_raw:project_id={fx.HN_VOICE_PROJECT}"
    assert mira.linkedin_url == fx.MIRA_LINKEDIN_HACKNATION


def test_normalizer_implements_the_source_normalizer_protocol() -> None:
    normalizer: SourceNormalizer = HacknationNormalizer(_projects())
    people = _people()
    record = BronzeRecord(
        table=PEOPLE_TABLE, row={key: as_sink(value) for key, value in people[0].items()}
    )
    (psr,) = normalizer.to_psr(record)
    assert psr.source == "hacknation"
    assert psr.source_key == fx.HN_LENA_KEY
    assert psr.keywords == ("ai", "pytorch", "robotics", "ros")
    assert normalizer.to_psr(BronzeRecord(table="bronze.github_users_raw", row={})) == []
