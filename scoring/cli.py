# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The scoring CLI: one subcommand per job, `--fixtures --dry-run` is CI-safe.

Jobs stay pure functions; this module only loads snapshots, composes deps
via scoring.deps, runs the job, and MERGEs the rows with registry-driven
keys. Data flows from --data-dir JSONL snapshots (fixtures/data by default),
which keeps the offline path byte-faithful to the golden files.
"""

from pathlib import Path
from typing import Final

import typer

from contracts.interfaces import CategoryScorer, InstitutionScorer
from contracts.models import Json, SinkRow
from scoring import scripted
from scoring.categories.base import scripted_registry
from scoring.categories.scorers import stage_a_registry
from scoring.deps import ScoringDeps, build_scoring_deps
from scoring.features import (
    DEFAULT_PROFILE,
    NO_OVERRIDES,
    FeatureRequest,
    build_person_features,
)
from scoring.funding import StaticCascadeFundedFounderResolver
from scoring.gaps import build_gaps
from scoring.institution_seed import build_institution_rows
from scoring.institutions import SeededInstitutionScorer
from scoring.memo import MemoRequest, build_memo
from scoring.pool import PoolAssembly, build_candidate_pool, pool_candidates
from scoring.rescore import RescoreRequest, ingest_interview
from scoring.snapshot import (
    GoldInputs,
    Row,
    SilverSnapshot,
    get_bool,
    get_float,
    load_gold_inputs,
    load_silver,
    require_str,
)
from scoring.stage_a import (
    StageAContext,
    collab_extras,
    feature_bundle,
    run_stage_a,
    venture_view,
)
from scoring.ventures import build_ventures, hackathon_extras
from scrapers.common.jsonutil import get_list, get_map, get_str
from scrapers.common.log import configure_logging
from scrapers.common.sink import DEFAULT_CATALOG
from tools.ddl_registry import coerce_rows, table_schema
from tools.llm import EMBEDDING_MODEL

DEFAULT_DATA_DIR: Final[str] = "fixtures/data"
LIVE_SCORER_VERSION: Final[str] = "stage-a-1"
LIVE_MEMO_VERSION: Final[str] = "memo-1"

app: Final[typer.Typer] = typer.Typer(add_completion=False, no_args_is_help=True)


class NoActiveRowError(ValueError):
    """No usable row was found for a required input table."""

    def __init__(self, table: str) -> None:
        """Name the empty input."""
        super().__init__(f"no usable row found in {table}; check --data-dir")


def _setup(
    *, fixtures: bool, dry_run: bool, catalog: str, data_dir: str, stage_b: bool = False
) -> tuple[ScoringDeps, SilverSnapshot, GoldInputs]:
    configure_logging()
    deps = build_scoring_deps(fixtures=fixtures, dry_run=dry_run, catalog=catalog, stage_b=stage_b)
    path = Path(data_dir)
    return deps, load_silver(path), load_gold_inputs(path)


def _upsert(deps: ScoringDeps, table: str, rows: list[SinkRow]) -> None:
    schema = table_schema(table)
    keys = list(schema.primary_key or ("run_id", "stage"))
    typed = coerce_rows(table, rows)
    result = deps.sink.upsert(table, typed, keys, variant_cols=schema.variant_cols)
    typer.echo(f"{table}: +{result.inserted} ~{result.updated}")


def _active_row(rows: tuple[Row, ...], table: str) -> Row:
    for row in rows:
        if get_bool(row, "is_active") is not False:
            return row
    raise NoActiveRowError(table)


def _pick_venture(gold: GoldInputs, venture_id: str | None) -> Row:
    for row in gold.ventures:
        if venture_id is None or row.get("venture_id") == venture_id:
            return row
    raise NoActiveRowError("gold.venture")


def _member_ids(gold: GoldInputs, venture_id: str) -> tuple[str, ...]:
    members = [row for row in gold.members if row.get("venture_id") == venture_id]
    members.sort(key=lambda row: get_float(row, "weight") or 0.0, reverse=True)
    return tuple(require_str(row, "person_id") for row in members)


def _float_list(row: dict[str, Json], key: str) -> list[float]:
    return [
        float(v)
        for v in get_list(row, key)
        if not isinstance(v, bool) and isinstance(v, int | float)
    ]


def _institution_scorer(deps: ScoringDeps, gold: GoldInputs) -> InstitutionScorer:
    rows = gold.institution_scores or tuple(build_institution_rows(now=deps.clock()))
    return SeededInstitutionScorer(list(rows), deps.log)


def _resolver(silver: SilverSnapshot) -> StaticCascadeFundedFounderResolver:
    return StaticCascadeFundedFounderResolver(
        list(silver.sogc), list(silver.officers), list(silver.companies)
    )


def _registry(
    deps: ScoringDeps, gold: GoldInputs, silver: SilverSnapshot, *, offline: bool
) -> dict[str, CategoryScorer]:
    if offline:
        return scripted_registry(scripted.fixture_category_results())
    del silver
    ideal = _active_row(gold.ideals, "gold.ideal_candidate")
    bundle = feature_bundle(gold.features)
    embeddings = {
        require_str(row, "person_id"): _float_list(dict(row), "profile_embedding")
        for row in gold.features
    }
    ideal_embedding = _float_list(dict(ideal), "embedding")
    return stage_a_registry(
        deps.llm,
        bundle.person_features,
        get_map(dict(ideal), "profile_json"),
        ideal_embedding,
        embeddings,
    )


def _stage_a_context(
    deps: ScoringDeps,
    silver: SilverSnapshot,
    gold: GoldInputs,
    venture_row: Row,
    *,
    offline: bool,
) -> StageAContext:
    venture_id = require_str(venture_row, "venture_id")
    members = tuple(row for row in gold.members if row.get("venture_id") == venture_id)
    member_ids = _member_ids(gold, venture_id)
    extras: dict[str, Json] = dict(collab_extras(silver, member_ids))
    extras["website_url"] = get_str(dict(venture_row), "website_url")
    extras.update(hackathon_extras(silver, venture_row))
    weights_row = _active_row(gold.weights, "gold.score_weights")
    ideal = _active_row(gold.ideals, "gold.ideal_candidate")
    return StageAContext(
        venture=venture_view(venture_row, members, extras),
        features=feature_bundle(gold.features),
        weights_row=weights_row,
        profile_id=get_str(dict(ideal), "profile_id"),
        registry=_registry(deps, gold, silver, offline=offline),
        prior_scores=gold.scores,
        model_version=scripted.SCORER_MODEL_VERSION if offline else LIVE_SCORER_VERSION,
        calibration=scripted.FIXTURE_CALIBRATION if offline else None,
    )


@app.command("seed-institutions")
def seed_institutions(  # pyright: ignore[reportUnusedFunction] - typer registers the command via the decorator
    *,
    fixtures: bool = False,
    dry_run: bool = False,
    catalog: str = DEFAULT_CATALOG,
) -> None:
    """Write the calibrated institution seed to gold.institution_score."""
    deps = build_scoring_deps(fixtures=fixtures, dry_run=dry_run, catalog=catalog)
    _upsert(deps, "gold.institution_score", build_institution_rows(now=deps.clock()))


@app.command()
def ventures(  # pyright: ignore[reportUnusedFunction] - typer registers the command via the decorator
    *,
    fixtures: bool = False,
    dry_run: bool = False,
    catalog: str = DEFAULT_CATALOG,
    data_dir: str = DEFAULT_DATA_DIR,
) -> None:
    """Build gold.venture and gold.venture_member from the silver snapshot."""
    deps, silver, gold = _setup(
        fixtures=fixtures, dry_run=dry_run, catalog=catalog, data_dir=data_dir
    )
    built = build_ventures(silver, gold.ventures, deps.llm, deps.clock)
    _upsert(deps, "gold.venture", built.venture_rows)
    _upsert(deps, "gold.venture_member", built.member_rows)


@app.command()
def features(  # pyright: ignore[reportUnusedFunction] - typer registers the command via the decorator
    *,
    fixtures: bool = False,
    dry_run: bool = False,
    catalog: str = DEFAULT_CATALOG,
    data_dir: str = DEFAULT_DATA_DIR,
    venture_id: str | None = None,
) -> None:
    """Compute gold.person_features for the venture members."""
    deps, silver, gold = _setup(
        fixtures=fixtures, dry_run=dry_run, catalog=catalog, data_dir=data_dir
    )
    offline = fixtures and dry_run
    venture_row = _pick_venture(gold, venture_id)
    request = FeatureRequest(
        person_ids=_member_ids(gold, require_str(venture_row, "venture_id")),
        snapshot=silver,
        institutions=_institution_scorer(deps, gold),
        llm=deps.llm,
        clock=deps.clock,
        profile=scripted.FIXTURE_FEATURE_PROFILE if offline else DEFAULT_PROFILE,
        overrides=scripted.FIXTURE_OVERRIDES if offline else NO_OVERRIDES,
        embedding_model=scripted.OFFLINE_EMBEDDING_MODEL if offline else EMBEDDING_MODEL,
    )
    _upsert(deps, "gold.person_features", build_person_features(request))


@app.command("stage-a")
def stage_a(  # pyright: ignore[reportUnusedFunction] - typer registers the command via the decorator
    *,
    fixtures: bool = False,
    dry_run: bool = False,
    catalog: str = DEFAULT_CATALOG,
    data_dir: str = DEFAULT_DATA_DIR,
    venture_id: str | None = None,
) -> None:
    """Run Stage A: venture_score plus the ranked venture_gaps."""
    deps, silver, gold = _setup(
        fixtures=fixtures, dry_run=dry_run, catalog=catalog, data_dir=data_dir
    )
    offline = fixtures and dry_run
    venture_row = _pick_venture(gold, venture_id)
    context = _stage_a_context(deps, silver, gold, venture_row, offline=offline)
    result = run_stage_a(context, clock=deps.clock, id_factory=deps.id_factory)
    _upsert(deps, "gold.venture_score", [result.score_row, *result.flipped_rows])
    gaps = build_gaps(context.venture.venture_id, context.weights_row, frozenset(), deps.clock())
    _upsert(deps, "gold.venture_gaps", gaps)
    typer.echo(
        f"final={result.final_score} confidence={result.confidence} tier={result.quality_tier}"
    )


@app.command()
def pool(  # pyright: ignore[reportUnusedFunction] - typer registers the command via the decorator
    *,
    fixtures: bool = False,
    dry_run: bool = False,
    catalog: str = DEFAULT_CATALOG,
    data_dir: str = DEFAULT_DATA_DIR,
    thesis_id: str | None = None,
) -> None:
    """Materialize gold.candidate_pool for the (active) thesis."""
    deps, silver, gold = _setup(
        fixtures=fixtures, dry_run=dry_run, catalog=catalog, data_dir=data_dir
    )
    thesis = (
        next((row for row in gold.theses if row.get("thesis_id") == thesis_id), None)
        if thesis_id is not None
        else _active_row(gold.theses, "gold.thesis")
    )
    if thesis is None:
        raise NoActiveRowError("gold.thesis")
    assembly = PoolAssembly(
        ventures=gold.ventures,
        members=gold.members,
        projects=silver.projects,
        companies=silver.companies,
        resolver=_resolver(silver),
        llm=deps.llm,
    )
    rows = build_candidate_pool(thesis, pool_candidates(assembly), deps.clock())
    _upsert(deps, "gold.candidate_pool", rows)


@app.command("stage-b")
def stage_b(  # pyright: ignore[reportUnusedFunction] - typer registers the command via the decorator
    *,
    fixtures: bool = False,
    dry_run: bool = False,
    venture_id: str | None = None,
) -> None:
    """Report the Stage-B deep-dive verdicts (scripted when offline)."""
    if not (fixtures and dry_run):
        typer.echo(
            "stage-b live runs need a warehouse plus either ANTHROPIC_API_KEY "
            "or LLM_BACKEND=claude-code (a signed-in Claude Code, no API "
            "credits); run with --fixtures --dry-run for the scripted path"
        )
        raise typer.Exit(code=1)
    del venture_id
    for name, verdict in scripted.fixture_category_results().items():
        typer.echo(f"{name}: score={verdict.score} method={verdict.method}")


@app.command()
def memo(  # pyright: ignore[reportUnusedFunction] - typer registers the command via the decorator
    *,
    fixtures: bool = False,
    dry_run: bool = False,
    catalog: str = DEFAULT_CATALOG,
    data_dir: str = DEFAULT_DATA_DIR,
    venture_id: str | None = None,
) -> None:
    """Generate the cited nine-section memo for one venture."""
    deps, _, gold = _setup(fixtures=fixtures, dry_run=dry_run, catalog=catalog, data_dir=data_dir)
    offline = fixtures and dry_run
    venture_row = _pick_venture(gold, venture_id)
    request = MemoRequest(
        venture_id=require_str(venture_row, "venture_id"),
        thesis_id=get_str(dict(venture_row), "thesis_id")
        or get_str(dict(_active_row(gold.theses, "gold.thesis")), "thesis_id"),
        run_id=deps.id_factory(),
        context={"name": require_str(venture_row, "name")},
        model_version=scripted.MEMO_MODEL_VERSION if offline else LIVE_MEMO_VERSION,
        prior_memos=gold.memos,
    )
    result = build_memo(request, llm=deps.llm, clock=deps.clock, id_factory=deps.id_factory)
    _upsert(deps, "gold.memo", [result.memo_row, *result.flipped_rows])


@app.command()
def rescore(  # pyright: ignore[reportUnusedFunction] - typer registers the command via the decorator
    *,
    fixtures: bool = False,
    dry_run: bool = False,
    catalog: str = DEFAULT_CATALOG,
    data_dir: str = DEFAULT_DATA_DIR,
    venture_id: str | None = None,
) -> None:
    """Ingest the completed interview and run the targeted rescore."""
    deps, silver, gold = _setup(
        fixtures=fixtures, dry_run=dry_run, catalog=catalog, data_dir=data_dir
    )
    offline = fixtures and dry_run
    venture_row = _pick_venture(gold, venture_id)
    interview = next(
        (row for row in gold.interviews if row.get("venture_id") == venture_row.get("venture_id")),
        None,
    )
    if interview is None:
        raise NoActiveRowError("gold.interview")
    context = _stage_a_context(deps, silver, gold, venture_row, offline=offline)
    request = RescoreRequest(
        interview=interview,
        context=context,
        memo=MemoRequest(
            venture_id=context.venture.venture_id,
            thesis_id=get_str(dict(_active_row(gold.theses, "gold.thesis")), "thesis_id"),
            run_id=deps.id_factory(),
            context={"name": context.venture.name},
            model_version=scripted.MEMO_MODEL_VERSION if offline else LIVE_MEMO_VERSION,
            prior_memos=gold.memos,
        ),
        prior_runs=gold.score_runs,
        snapshot=silver,
    )
    outcome = ingest_interview(
        request,
        llm=deps.llm,
        institutions=_institution_scorer(deps, gold),
        clock=deps.clock,
        id_factory=deps.id_factory,
    )
    _upsert(deps, "gold.score_run", [outcome.run_row])
    if outcome.score_rows:
        _upsert(deps, "gold.venture_score", list(outcome.score_rows))
    if outcome.memo_rows:
        _upsert(deps, "gold.memo", list(outcome.memo_rows))
    typer.echo(f"rescore status={outcome.status}")
