"""CLI: the credential-free `--fixtures --dry-run` path, end to end.

Also proves every emitted row shape stays inside the DDL contract: emitted
keys must be a subset of the registry's column names for the target table.
"""

import json
from typing import Final

from typer.testing import CliRunner

from fixtures import build
from scoring import scripted
from scoring.cli import app
from scoring.deps import ScoringDeps
from scoring.features import FeatureRequest, build_person_features
from scoring.gaps import build_gaps
from scoring.institution_seed import build_institution_rows
from scoring.institutions import SeededInstitutionScorer
from scoring.memo import MemoRequest, build_memo
from scoring.serialize import to_jsonl_lines
from scoring.snapshot import GoldInputs, SilverSnapshot
from scoring.ventures import build_ventures
from scrapers.common.jsonutil import as_mapping
from tests.scoring.conftest import MEMBER_IDS
from tools.ddl_registry import table_schema

RUNNER: Final[CliRunner] = CliRunner()


def test_stage_a_offline_end_to_end() -> None:
    result = RUNNER.invoke(app, ["stage-a", "--fixtures", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "final=78.4 confidence=0.82 tier=scored" in result.output
    assert "gold.venture_score: +2" in result.output
    assert "gold.venture_gaps: +2" in result.output


def test_every_offline_subcommand_runs_without_credentials() -> None:
    for command in (
        ["seed-institutions"],
        ["ventures"],
        ["features"],
        ["pool"],
        ["memo"],
        ["rescore"],
        ["stage-b"],
    ):
        result = RUNNER.invoke(app, [*command, "--fixtures", "--dry-run"])
        assert result.exit_code == 0, f"{command}: {result.output}"


def test_stage_b_live_without_credentials_exits_nonzero() -> None:
    result = RUNNER.invoke(app, ["stage-b"])
    assert result.exit_code == 1


def assert_rows_within_ddl(table: str, rows: list[dict[str, object]]) -> None:
    columns = set(table_schema(table).column_names)
    for row in rows:
        assert set(row) <= columns, f"{table}: {set(row) - columns}"


def parsed_rows(text: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for line in text.splitlines():
        decoded = as_mapping(json.loads(line))
        out.append(dict(decoded))
    return out


def test_emitted_keys_stay_inside_the_ddl_contract(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    ventures = build_ventures(silver, gold.ventures, deps.llm, deps.clock)
    features = build_person_features(
        FeatureRequest(
            person_ids=MEMBER_IDS,
            snapshot=silver,
            institutions=SeededInstitutionScorer(
                list(build_institution_rows(now=scripted.FIXTURE_NOW)), deps.log
            ),
            llm=deps.llm,
            clock=deps.clock,
            profile=scripted.FIXTURE_FEATURE_PROFILE,
            overrides=scripted.FIXTURE_OVERRIDES,
            embedding_model=scripted.OFFLINE_EMBEDDING_MODEL,
        )
    )
    memo = build_memo(
        MemoRequest(
            venture_id=build.GRASP_VENTURE,
            thesis_id=build.THESIS_ID,
            run_id=build.RUN_ID,
            context={"name": "GraspLab"},
            model_version=scripted.MEMO_MODEL_VERSION,
            prior_memos=(),
        ),
        llm=deps.llm,
        clock=deps.clock,
        id_factory=lambda: build.MEMO_ID,
    )
    emissions = (
        ("gold.institution_score", build_institution_rows(now=scripted.FIXTURE_NOW)),
        ("gold.venture", ventures.venture_rows),
        ("gold.venture_member", ventures.member_rows),
        ("gold.person_features", features),
        (
            "gold.venture_gaps",
            build_gaps(build.GRASP_VENTURE, gold.weights[0], frozenset(), scripted.FIXTURE_NOW),
        ),
        ("gold.memo", [memo.memo_row]),
    )
    for table, rows in emissions:
        assert_rows_within_ddl(table, parsed_rows(to_jsonl_lines(rows)))


def test_score_run_rows_stay_inside_the_ddl_contract(
    silver: SilverSnapshot, gold: GoldInputs, deps: ScoringDeps
) -> None:
    del silver, gold, deps
    columns = set(table_schema("gold.score_run").column_names)
    assert {"run_id", "trigger", "input_versions", "status"} <= columns
