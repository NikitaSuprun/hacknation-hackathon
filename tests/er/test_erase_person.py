"""T12: erasure plan/execute with recording fakes; suppression stops re-runs."""

from typing import Final

import pytest

from contracts.models import Json, SinkRow, UpsertResult
from er.normalize import normalize_bronze, suppressed_keys
from er.offline import frozen_clock
from er.pipeline import ErInputs
from fixtures import build as fx
from tests.er.conftest import fixture_rows
from tools.erase_person import (
    ErasurePlan,
    UnknownPersonError,
    execute,
    plan_erasure,
    source_key_hash,
)

ERASURE_ID: Final[str] = "eeeeeeee-0000-4000-8000-000000000001"


class RecordingRunner:
    """Records every executed statement."""

    def __init__(self) -> None:
        self.statements: Final[list[str]] = []

    def execute(self, statement: str) -> list[tuple[object, ...]]:
        self.statements.append(statement)
        return []


class RecordingSink:
    """Records every upsert call."""

    def __init__(self) -> None:
        self.calls: Final[list[tuple[str, list[SinkRow], list[str]]]] = []

    def upsert(
        self,
        table: str,
        rows: list[SinkRow],
        keys: list[str],
        *,
        variant_cols: frozenset[str] = frozenset(),
        hash_col: str = "content_hash",
    ) -> UpsertResult:
        del variant_cols, hash_col
        self.calls.append((table, rows, keys))
        return UpsertResult(
            table=table, inserted=len(rows), updated=0, skipped_unchanged=0, suppressed=0
        )


def _person_tables() -> dict[str, list[dict[str, Json]]]:
    tables = (
        "silver.person",
        "silver.person_source_link",
        "silver.person_source_record",
        "silver.contribution",
        "silver.authorship",
        "silver.officer",
        "silver.person_connection",
        "gold.person_features",
        "gold.venture_member",
        "ops.er_review_queue",
        "bronze.github_users_raw",
        "bronze.github_commits_raw",
        "bronze.hacknation_people_raw",
    )
    return {table: list(fixture_rows(table)) for table in tables}


def _lena_plan() -> ErasurePlan:
    return plan_erasure(
        fx.LENA,
        _person_tables(),
        scope="full",
        clock=frozen_clock,
        actor="dpo",
        erasure_id=ERASURE_ID,
    )


def test_plan_covers_all_four_schemas_and_hashes_keys() -> None:
    plan = _lena_plan()
    schemas = {op.table.split(".")[0] for op in plan.deletes}
    assert schemas == {"bronze", "silver", "gold", "ops"}
    suppression = plan.upserts["ops.erasure_suppression"]
    hashes = {(str(row["source"]), str(row["source_key_hash"])) for row in suppression}
    assert ("github", source_key_hash("501001")) in hashes
    assert ("openalex_author", source_key_hash("A5000000001")) in hashes
    assert ("zefix_officer", source_key_hash(f"{fx.GRASP_UID}:fischer lena")) in hashes
    assert ("hacknation", source_key_hash(fx.HN_LENA_USER)) in hashes
    hacknation_ops = [op for op in plan.deletes if op.table == "bronze.hacknation_people_raw"]
    assert [op.where for op in hacknation_ops] == [f"user_id IN ('{fx.HN_LENA_USER}')"]
    # The fixture suppression row proves the exact hash derivation.
    assert source_key_hash("999001") == fx.SUPPRESSED_KEY_HASH
    (tombstone,) = plan.upserts["silver.person"]
    assert tombstone["status"] == "erased"
    assert tombstone["full_name"] is None
    assert tombstone["primary_email"] is None
    (log_row,) = plan.upserts["ops.erasure_log"]
    assert log_row["erasure_id"] == ERASURE_ID
    assert log_row["executed_by"] == "dpo"


def test_execute_runs_deletes_and_upserts() -> None:
    plan = _lena_plan()
    runner = RecordingRunner()
    sink = RecordingSink()
    execute(plan, runner, sink, catalog="dealflow_dev")
    assert len(runner.statements) == len(plan.deletes)
    assert all(s.startswith("DELETE FROM dealflow_dev.") for s in runner.statements)
    assert {call[0] for call in sink.calls} == {
        "silver.person",
        "ops.erasure_log",
        "ops.erasure_suppression",
    }


def test_stage0_rerun_resurrects_nothing(inputs: ErInputs) -> None:
    plan = _lena_plan()
    suppressed = suppressed_keys(plan.upserts["ops.erasure_suppression"])
    records = normalize_bronze(
        {
            "bronze.github_users_raw": inputs.github_users,
            "bronze.github_commits_raw": inputs.github_commits,
            "bronze.github_repos_raw": inputs.github_repos,
            "bronze.arxiv_papers_raw": inputs.arxiv_papers,
            "bronze.openalex_works_raw": inputs.openalex_works,
            "bronze.zefix_companies_raw": inputs.zefix_companies,
            "bronze.zefix_sogc_raw": inputs.zefix_sogc,
            "bronze.hacknation_people_raw": inputs.hacknation_people,
            "bronze.hacknation_projects_raw": inputs.hacknation_projects,
            "bronze.hacknation_cvs_raw": inputs.hacknation_cvs,
        },
        suppressed=suppressed,
    )
    keys = {(record.source, record.source_key) for record in records}
    assert ("github", "501001") not in keys
    assert ("openalex_author", "A5000000001") not in keys
    assert ("zefix_officer", f"{fx.GRASP_UID}:fischer lena") not in keys
    assert ("hacknation", fx.HN_LENA_USER) not in keys
    # Everyone else survives.
    assert ("github", "501003") in keys
    assert ("hacknation", fx.HN_SELIN_USER) in keys


def test_hacknation_person_erasure_notes_the_cv_pointer() -> None:
    plan = plan_erasure(
        fx.SELIN,
        _person_tables(),
        scope="full",
        clock=frozen_clock,
        actor="dpo",
        erasure_id=ERASURE_ID,
    )
    hacknation_ops = [op for op in plan.deletes if op.table == "bronze.hacknation_people_raw"]
    assert [op.where for op in hacknation_ops] == [f"user_id IN ('{fx.HN_SELIN_USER}')"]
    suppression = plan.upserts["ops.erasure_suppression"]
    hashes = {(str(row["source"]), str(row["source_key_hash"])) for row in suppression}
    assert ("hacknation", source_key_hash(fx.HN_SELIN_USER)) in hashes
    (log_row,) = plan.upserts["ops.erasure_log"]
    assert log_row["notes"] == f"purge CV file from UC Volume: {fx.SELIN_CV_URL}"
    (tombstone,) = plan.upserts["silver.person"]
    assert tombstone["cv_url"] is None


def test_unknown_person_raises() -> None:
    with pytest.raises(UnknownPersonError):
        plan_erasure(
            "no-such-person",
            {"silver.person": []},
            scope="full",
            clock=frozen_clock,
            actor="dpo",
            erasure_id=ERASURE_ID,
        )
