# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Interview-completion sync: feed the interview into the WS-E targeted rescore.

Rows come from the DataStore (fixtures overlay or warehouse), get shaped into
the pure scoring inputs, and scoring.rescore.ingest_interview produces the
score/memo/run rows we merge back. Offline runs use the scripted category
registry and fixture calibration, live runs the real Stage-A registry.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.store import DataStore
from contracts.interfaces import CategoryScorer, InstitutionScorer, LLMClient
from contracts.models import Json
from scoring import scripted
from scoring.categories.base import CATEGORY_NAMES, scripted_registry, weight_column
from scoring.categories.scorers import stage_a_registry
from scoring.institution_seed import build_institution_rows
from scoring.institutions import SeededInstitutionScorer
from scoring.memo import MemoRequest
from scoring.rescore import RescoreOutcome, RescoreRequest, ingest_interview
from scoring.snapshot import (
    GoldInputs,
    Row,
    SilverSnapshot,
    get_bool,
    get_float,
    require_str,
)
from scoring.stage_a import StageAContext, collab_extras, feature_bundle, venture_view
from scrapers.common.jsonutil import get_list, get_map, get_str
from scrapers.common.log import get_logger

LIVE_SCORER_VERSION: Final[str] = "stage-a-1"
LIVE_MEMO_VERSION: Final[str] = "memo-1"

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


class NoActiveRowError(ValueError):
    """No usable row was found for a required input table."""

    def __init__(self, table: str) -> None:
        """Name the empty input."""
        super().__init__(f"no usable row found in {table}")


@dataclass(frozen=True, slots=True)
class RescoreDeps:
    """The injected impurities of one interview rescore."""

    llm: LLMClient
    clock: Clock
    id_factory: IdFactory
    offline: bool


def _tuple_rows(store: DataStore, name: str) -> tuple[Row, ...]:
    return tuple(store.rows(name))


def load_silver_snapshot(store: DataStore) -> SilverSnapshot:
    """The silver snapshot as the store currently sees it.

    Args:
        store: The data seam.

    Returns:
        The frozen snapshot.
    """
    return SilverSnapshot(
        projects=_tuple_rows(store, "silver.project"),
        companies=_tuple_rows(store, "silver.company"),
        publications=_tuple_rows(store, "silver.publication"),
        contributions=_tuple_rows(store, "silver.contribution"),
        authorships=_tuple_rows(store, "silver.authorship"),
        officers=_tuple_rows(store, "silver.officer"),
        persons=_tuple_rows(store, "silver.person"),
        connections=_tuple_rows(store, "silver.person_connection"),
        sogc=_tuple_rows(store, "bronze.zefix_sogc_raw"),
        hacknation_projects=_tuple_rows(store, "bronze.hacknation_projects_raw"),
        person_links=_tuple_rows(store, "silver.person_source_link"),
    )


def load_gold_snapshot(store: DataStore) -> GoldInputs:
    """The gold-side scoring inputs as the store currently sees them.

    Args:
        store: The data seam.

    Returns:
        The frozen gold inputs.
    """
    return GoldInputs(
        theses=_tuple_rows(store, "gold.thesis"),
        weights=_tuple_rows(store, "gold.score_weights"),
        ideals=_tuple_rows(store, "gold.ideal_candidate"),
        ventures=_tuple_rows(store, "gold.venture"),
        members=_tuple_rows(store, "gold.venture_member"),
        scores=_tuple_rows(store, "gold.venture_score"),
        interviews=_tuple_rows(store, "gold.interview"),
        features=_tuple_rows(store, "gold.person_features"),
        institution_scores=_tuple_rows(store, "gold.institution_score"),
        memos=_tuple_rows(store, "gold.memo"),
        score_runs=_tuple_rows(store, "gold.score_run"),
    )


def active_row(rows: tuple[Row, ...], table: str) -> Row:
    """The first row not explicitly deactivated.

    Args:
        rows: The candidate rows.
        table: Table name for the error message.

    Returns:
        The active row.

    Raises:
        NoActiveRowError: If every row is inactive or none exist.
    """
    for row in rows:
        if get_bool(row, "is_active") is not False:
            return row
    raise NoActiveRowError(table)


def _member_ids(gold: GoldInputs, venture_id: str) -> tuple[str, ...]:
    members = [row for row in gold.members if row.get("venture_id") == venture_id]
    members.sort(key=lambda row: get_float(row, "weight") or 0.0, reverse=True)
    return tuple(require_str(row, "person_id") for row in members)


def _float_list(row: dict[str, Json], key: str) -> list[float]:
    return [
        float(item)
        for item in get_list(row, key)
        if not isinstance(item, bool) and isinstance(item, int | float)
    ]


def build_institutions(gold: GoldInputs, clock: Clock) -> InstitutionScorer:
    """The calibrated institution scorer over gold rows (or the seed).

    Args:
        gold: The gold inputs.
        clock: Time source for a fresh seed when gold has no rows.

    Returns:
        The scorer.
    """
    rows = gold.institution_scores or tuple(build_institution_rows(now=clock()))
    return SeededInstitutionScorer(list(rows), get_logger("app"))


def _registry(deps: RescoreDeps, gold: GoldInputs) -> dict[str, CategoryScorer]:
    if deps.offline:
        return scripted_registry(scripted.fixture_category_results())
    ideal = active_row(gold.ideals, "gold.ideal_candidate")
    bundle = feature_bundle(gold.features)
    embeddings = {
        require_str(row, "person_id"): _float_list(dict(row), "profile_embedding")
        for row in gold.features
    }
    return stage_a_registry(
        deps.llm,
        bundle.person_features,
        get_map(dict(ideal), "profile_json"),
        _float_list(dict(ideal), "embedding"),
        embeddings,
    )


def _stage_a_context(
    deps: RescoreDeps, silver: SilverSnapshot, gold: GoldInputs, venture_row: Row
) -> StageAContext:
    venture_id = require_str(venture_row, "venture_id")
    members = tuple(row for row in gold.members if row.get("venture_id") == venture_id)
    extras: dict[str, Json] = dict(collab_extras(silver, _member_ids(gold, venture_id)))
    extras["website_url"] = get_str(dict(venture_row), "website_url")
    ideal = active_row(gold.ideals, "gold.ideal_candidate")
    return StageAContext(
        venture=venture_view(venture_row, members, extras),
        features=feature_bundle(gold.features),
        weights_row=active_row(gold.weights, "gold.score_weights"),
        profile_id=get_str(dict(ideal), "profile_id"),
        registry=_registry(deps, gold),
        prior_scores=gold.scores,
        model_version=scripted.SCORER_MODEL_VERSION if deps.offline else LIVE_SCORER_VERSION,
        calibration=scripted.FIXTURE_CALIBRATION if deps.offline else None,
    )


def _venture_row(gold: GoldInputs, venture_id: str) -> Row:
    for row in gold.ventures:
        if row.get("venture_id") == venture_id:
            return row
    raise NoActiveRowError("gold.venture")


def run_interview_rescore(
    store: DataStore, deps: RescoreDeps, interview_row: Mapping[str, Json]
) -> RescoreOutcome:
    """Ingest one completed interview and merge the rescore output back.

    Args:
        store: The data seam (read inputs, write score/memo/run rows).
        deps: The injected impurities.
        interview_row: The gold.interview row that just completed.

    Returns:
        The rescore outcome (skipped duplicates write only the run row).
    """
    silver = load_silver_snapshot(store)
    gold = load_gold_snapshot(store)
    venture_id = require_str(interview_row, "venture_id")
    venture_row = _venture_row(gold, venture_id)
    context = _stage_a_context(deps, silver, gold, venture_row)
    request = RescoreRequest(
        interview=interview_row,
        context=context,
        memo=MemoRequest(
            venture_id=venture_id,
            thesis_id=get_str(dict(active_row(gold.theses, "gold.thesis")), "thesis_id"),
            run_id=deps.id_factory(),
            context={"name": context.venture.name},
            model_version=scripted.MEMO_MODEL_VERSION if deps.offline else LIVE_MEMO_VERSION,
            prior_memos=gold.memos,
        ),
        prior_runs=gold.score_runs,
        snapshot=silver,
    )
    outcome = ingest_interview(
        request,
        llm=deps.llm,
        institutions=build_institutions(gold, deps.clock),
        clock=deps.clock,
        id_factory=deps.id_factory,
    )
    store.upsert("gold.score_run", [outcome.run_row])
    if outcome.score_rows:
        store.upsert("gold.venture_score", list(outcome.score_rows))
    if outcome.memo_rows:
        store.upsert("gold.memo", list(outcome.memo_rows))
    return outcome


def client_final_score(
    weights_row: Mapping[str, Json], ranked_row: Mapping[str, Json]
) -> float | None:
    """Python mirror of the client-side re-rank formula in app/static/app.js.

    final = sum(w_i * s_i) over scored categories (ideal_match included via
    w_ideal_match), with the weights renormalized over the categories that
    actually carry a score — byte-for-byte the JS slider math.

    Args:
        weights_row: A gold.score_weights row.
        ranked_row: A gold.v_ranked_ventures row.

    Returns:
        The recomputed final score, or None when nothing is scored.
    """
    pairs: list[tuple[float, float]] = []
    for name in CATEGORY_NAMES:
        column = "ideal_match" if name == "ideal_match" else f"s_{name}"
        score = get_float(ranked_row, column)
        weight = get_float(weights_row, weight_column(name))
        if score is not None and weight is not None:
            pairs.append((weight, score))
    total = sum(weight for weight, _ in pairs)
    if total <= 0.0:
        return None
    return round(sum(weight * score for weight, score in pairs) / total, 1)
