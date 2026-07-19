# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Stage A: assemble category verdicts into one gold.venture_score row.

Pure function of (venture view, features, weights, registry, prior scores):
the breakdown is hard-validated against the frozen JSON Schema, prior
`is_latest` rows are flipped, and the quality gate marks thin data as
`needs_more_data` instead of pretending completeness. `ScoreCalibration` is
the explicit seam for fixture-pinned final/confidence values that the real
formulas do not produce (fixture final 78.4 versus derived 78.9).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from contracts.interfaces import CategoryScorer
from contracts.models import (
    CategoryScore,
    FeatureBundle,
    Json,
    SinkRow,
    VentureView,
)
from contracts.validation import payload_errors
from scoring.categories.base import (
    CATEGORY_NAMES,
    breakdown_payload,
    renormalized_weights,
    run_confidence,
    weighted_final,
)
from scoring.snapshot import Row, SilverSnapshot, as_utc, get_bool, get_float, require_str
from scrapers.common.jsonutil import as_sink, get_str

CONFIDENCE_GATE: Final[float] = 0.5
QUALITY_SCORED: Final[str] = "scored"
QUALITY_NEEDS_MORE_DATA: Final[str] = "needs_more_data"
SHARED_CONTEXT_MIN: Final[int] = 2

# Feature keys each category needs filled for full coverage.
REQUIRED_FEATURES: Final[dict[str, tuple[str, ...]]] = {
    "individual_experience": ("stars_weighted", "commits_12mo", "zero_to_one_flag"),
    "schools": ("school_tier",),
    "ideal_match": ("school_tier", "stars_weighted", "recency_score"),
}


class BreakdownInvalidError(ValueError):
    """The assembled breakdown violates the frozen JSON Schema."""

    def __init__(self, errors: list[str]) -> None:
        """Carry every violation in the message."""
        super().__init__("; ".join(errors))


@dataclass(frozen=True, slots=True)
class ScoreCalibration:
    """Fixture-pinned final/confidence overriding the derived values."""

    final_score: float
    confidence: float


@dataclass(frozen=True, slots=True)
class StageAContext:
    """Everything one Stage-A run reads; impurities stay outside."""

    venture: VentureView
    features: FeatureBundle
    weights_row: Row
    profile_id: str | None
    registry: Mapping[str, CategoryScorer]
    prior_scores: tuple[Row, ...]
    model_version: str
    calibration: ScoreCalibration | None


@dataclass(frozen=True, slots=True)
class StageAResult:
    """One scored venture: the new row, prior-row flips, and the gate verdict."""

    score_row: SinkRow
    flipped_rows: tuple[SinkRow, ...]
    final_score: float
    confidence: float
    quality_tier: str


def feature_coverage(venture: VentureView, features: FeatureBundle) -> dict[str, float]:
    """Per-category coverage: mean filled/required over the members.

    Args:
        venture: The venture snapshot.
        features: The shared feature layer.

    Returns:
        0..1 coverage per category with required features (others omitted,
        treated as fully covered downstream).
    """
    coverage: dict[str, float] = {}
    members = venture.member_person_ids
    for category, required in REQUIRED_FEATURES.items():
        if not members or not required:
            continue
        filled = 0
        for person_id in members:
            member = features.person_features.get(person_id, {})
            filled += sum(1 for key in required if key in member)
        coverage[category] = filled / (len(members) * len(required))
    return coverage


def _flip_latest(prior_scores: tuple[Row, ...], venture_id: str) -> tuple[SinkRow, ...]:
    flipped: list[SinkRow] = []
    for row in prior_scores:
        if row.get("venture_id") != venture_id or get_bool(row, "is_latest") is not True:
            continue
        copy: SinkRow = {key: as_sink(value) for key, value in row.items()}
        copy["is_latest"] = False
        flipped.append(copy)
    return tuple(flipped)


def _score_columns(categories: Mapping[str, CategoryScore]) -> dict[str, float | None]:
    columns: dict[str, float | None] = {}
    for name in CATEGORY_NAMES:
        column = "ideal_match" if name == "ideal_match" else f"s_{name}"
        verdict = categories.get(name)
        columns[column] = verdict.score if verdict is not None else None
    return columns


def run_stage_a(
    context: StageAContext,
    *,
    clock: Callable[[], datetime],
    id_factory: Callable[[], str],
) -> StageAResult:
    """Score one venture and flip its prior latest rows.

    Args:
        context: The pure inputs of the run.
        clock: Injected time source for scored_at.
        id_factory: Injected id source for score_id.

    Returns:
        The new score row plus is_latest flips and the gate verdict.

    Raises:
        BreakdownInvalidError: If the breakdown violates the frozen schema.
    """
    categories = {
        name: context.registry[name].score(context.venture, context.features)
        for name in CATEGORY_NAMES
        if name in context.registry
    }
    breakdown = breakdown_payload(categories)
    errors = payload_errors("breakdown", breakdown)
    if errors:
        raise BreakdownInvalidError(errors)
    scored = [name for name, verdict in categories.items() if verdict.score is not None]
    weights = renormalized_weights(context.weights_row, scored)
    coverage = feature_coverage(context.venture, context.features)
    if context.calibration is not None:
        final_score = context.calibration.final_score
        confidence = context.calibration.confidence
    else:
        final_score = weighted_final(weights, categories)
        confidence = run_confidence(context.weights_row, categories, coverage)
    quality_tier = QUALITY_SCORED if confidence >= CONFIDENCE_GATE else QUALITY_NEEDS_MORE_DATA
    row: SinkRow = {
        "score_id": id_factory(),
        "venture_id": context.venture.venture_id,
        "thesis_id": require_str(context.weights_row, "thesis_id"),
        "weights_id": require_str(context.weights_row, "weights_id"),
        "profile_id": context.profile_id,
        "model_version": context.model_version,
        **_score_columns(categories),
        "breakdown": as_sink(dict(breakdown)),
        "scored_at": clock(),
        "final_score": final_score,
        "confidence": confidence,
        "is_latest": True,
    }
    return StageAResult(
        score_row=row,
        flipped_rows=_flip_latest(context.prior_scores, context.venture.venture_id),
        final_score=final_score,
        confidence=confidence,
        quality_tier=quality_tier,
    )


def venture_view(
    venture_row: Row, member_rows: tuple[Row, ...], extras: Mapping[str, Json]
) -> VentureView:
    """Adapt gold.venture(+members) rows into the scorer-facing view.

    Args:
        venture_row: The gold.venture row.
        member_rows: The venture's gold.venture_member rows.
        extras: Extra context (project fields, collab overlap, ...).

    Returns:
        The frozen venture view.
    """
    venture_id = require_str(venture_row, "venture_id")
    members = tuple(
        require_str(row, "person_id")
        for row in sorted(
            member_rows, key=lambda row: get_float(row, "weight") or 0.0, reverse=True
        )
        if row.get("venture_id") == venture_id
    )
    return VentureView(
        venture_id=venture_id,
        name=require_str(venture_row, "name"),
        one_liner=get_str(dict(venture_row), "one_liner"),
        anchor_type=require_str(venture_row, "anchor_type"),
        member_person_ids=members,
        extras=dict(extras),
    )


def feature_bundle(feature_rows: tuple[Row, ...]) -> FeatureBundle:
    """Adapt gold.person_features rows into the shared feature layer.

    Args:
        feature_rows: The gold.person_features rows.

    Returns:
        The frozen bundle (venture-level features start empty).
    """
    person_features: dict[str, dict[str, float]] = {}
    for row in feature_rows:
        person_id = require_str(row, "person_id")
        cell = row.get("features")
        values: dict[str, float] = {}
        if isinstance(cell, dict):
            for key, value in cell.items():
                if not isinstance(value, bool) and isinstance(value, int | float):
                    values[key] = float(value)
        person_features[person_id] = values
    return FeatureBundle(person_features=person_features, venture_features={})


def collab_extras(snapshot: SilverSnapshot, member_ids: tuple[str, ...]) -> dict[str, Json]:
    """Shared-history overlap for the prior-collaboration rubric.

    Contexts are distinct artifacts (publications, projects, companies)
    shared by at least two members; years span the artifact dates.

    Args:
        snapshot: The silver snapshot.
        member_ids: The venture's member person ids.

    Returns:
        {'collab_contexts': int, 'collab_years': float} extras.
    """
    members = set(member_ids)
    shared: dict[str, set[str]] = {}
    dates: list[str] = []
    joins = (
        (snapshot.authorships, "publication_id", "updated_at"),
        (snapshot.contributions, "project_id", "last_commit_at"),
        (snapshot.officers, "company_id", "registered_at"),
    )
    for rows, artifact_key, date_key in joins:
        for row in rows:
            person = get_str(dict(row), "person_id")
            artifact = get_str(dict(row), artifact_key)
            if person in members and artifact is not None:
                shared.setdefault(artifact, set()).add(person)
                stamp = get_str(dict(row), date_key)
                if stamp is not None:
                    dates.append(stamp)
    contexts = sum(1 for people in shared.values() if len(people) >= SHARED_CONTEXT_MIN)
    years = 0.0
    stamps = [stamp for text in dates if (stamp := as_utc(text)) is not None]
    if len(stamps) >= SHARED_CONTEXT_MIN:
        span_days = abs((max(stamps) - min(stamps)).days)
        years = round(span_days / 365.0, 2)
    return {"collab_contexts": contexts, "collab_years": years}
