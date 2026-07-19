# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Interview ingestion and the idempotent targeted rescore.

A completed interview validates against the frozen interview schema, maps
onto the scoring inputs (education -> school_tier, traction claims release
the traction cap, funding answer -> pool signal), and triggers a targeted
Stage-A rerun plus memo regeneration. gold.score_run records every run with a
content-hash fingerprint of its inputs; ingesting the same interview over the
same snapshot again is a skipped_duplicate that writes no score or memo rows.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final

from contracts.interfaces import InstitutionScorer, LLMClient
from contracts.models import FeatureBundle, Json, SinkRow
from contracts.validation import payload_errors
from scoring.funding import interview_funding_signal
from scoring.memo import MemoRequest, MemoResult, build_memo
from scoring.snapshot import Row, SilverSnapshot, snapshot_hash
from scoring.stage_a import StageAContext, run_stage_a
from scrapers.common.jsonutil import as_mapping, as_sink, get_list, get_map, get_str
from tools.db import content_hash

TRIGGER_INTERVIEW: Final[str] = "interview"
STATUS_OK: Final[str] = "ok"
STATUS_SKIPPED: Final[str] = "skipped_duplicate"


class InterviewInvalidError(ValueError):
    """The interview's extracted payload violates the frozen schema."""

    def __init__(self, errors: list[str]) -> None:
        """Carry every violation in the message."""
        super().__init__("; ".join(errors))


@dataclass(frozen=True, slots=True)
class RescoreRequest:
    """Everything one interview-triggered rescore reads."""

    interview: Row
    context: StageAContext
    memo: MemoRequest
    prior_runs: tuple[Row, ...]
    snapshot: SilverSnapshot


@dataclass(frozen=True, slots=True)
class RescoreOutcome:
    """What the ingest produced: the ledger row and any new gold rows."""

    status: str
    run_row: SinkRow
    score_rows: tuple[SinkRow, ...]
    memo_rows: tuple[SinkRow, ...]
    funding_signal: str | None


def _education_tiers(extracted: Row, institutions: InstitutionScorer) -> list[float]:
    tiers: list[float] = []
    for entry in get_list(dict(extracted), "education"):
        institution = get_str(as_mapping(entry), "institution")
        if institution is None:
            continue
        scored = institutions.score(institution, "university")
        if scored.prestige is not None:
            tiers.append(scored.score / 100.0)
    return tiers


def _adjusted_features(
    bundle: FeatureBundle, person_id: str | None, tiers: list[float]
) -> FeatureBundle:
    if not tiers or person_id is None:
        return bundle
    features = {pid: dict(values) for pid, values in bundle.person_features.items()}
    member = features.setdefault(person_id, {})
    member["school_tier"] = max(member.get("school_tier", 0.0), *tiers)
    return FeatureBundle(person_features=features, venture_features=dict(bundle.venture_features))


def _adjusted_context(
    request: RescoreRequest, extracted: Row, institutions: InstitutionScorer
) -> StageAContext:
    context = request.context
    person_id = get_str(dict(request.interview), "person_id")
    tiers = _education_tiers(extracted, institutions)
    features = _adjusted_features(context.features, person_id, tiers)
    venture = context.venture
    if get_list(dict(extracted), "traction_claims"):
        extras: dict[str, Json] = dict(venture.extras)
        extras["traction_confirmed"] = True
        venture = replace(venture, extras=extras)
    return replace(context, features=features, venture=venture)


def _fingerprint(request: RescoreRequest, extracted: Row) -> tuple[dict[str, Json], str]:
    versions: dict[str, Json] = {
        "trigger": TRIGGER_INTERVIEW,
        "interview_id": get_str(dict(request.interview), "interview_id"),
        "extracted_hash": content_hash(dict(extracted)),
        "snapshot_hash": snapshot_hash(request.snapshot),
        "venture_id": request.context.venture.venture_id,
    }
    return versions, content_hash(versions)


def _is_duplicate(prior_runs: tuple[Row, ...], fingerprint: str) -> bool:
    for row in prior_runs:
        versions = get_map(dict(row), "input_versions")
        if row.get("status") == STATUS_OK and versions.get("fingerprint") == fingerprint:
            return True
    return False


def _run_row(
    request: RescoreRequest,
    versions: dict[str, Json],
    status: str,
    run_id: str,
    now: datetime,
) -> SinkRow:
    return {
        "run_id": run_id,
        "trigger": TRIGGER_INTERVIEW,
        "venture_id": request.context.venture.venture_id,
        "thesis_id": request.memo.thesis_id,
        "input_versions": as_sink(dict(versions)),
        "status": status,
        "started_at": now,
        "finished_at": now,
    }


def ingest_interview(
    request: RescoreRequest,
    *,
    llm: LLMClient,
    institutions: InstitutionScorer,
    clock: Callable[[], datetime],
    id_factory: Callable[[], str],
) -> RescoreOutcome:
    """Validate an interview and run the targeted rescore, idempotently.

    The id factory is consumed in order: score_id, then memo_id, then the
    score_run id (a duplicate consumes only the run id).

    Args:
        request: The pure inputs of the ingest.
        llm: The LLM seam for the memo regeneration.
        institutions: Calibrated scorer for interviewed education.
        clock: Injected time source.
        id_factory: Injected id source.

    Returns:
        The outcome; skipped duplicates carry no score or memo rows.

    Raises:
        InterviewInvalidError: If the extracted payload violates the schema.
    """
    extracted: Row = get_map(dict(request.interview), "extracted")
    errors = payload_errors("interview", dict(extracted))
    if errors:
        raise InterviewInvalidError(errors)
    versions, fingerprint = _fingerprint(request, extracted)
    versions["fingerprint"] = fingerprint
    now = clock()
    if _is_duplicate(request.prior_runs, fingerprint):
        return RescoreOutcome(
            status=STATUS_SKIPPED,
            run_row=_run_row(request, versions, STATUS_SKIPPED, id_factory(), now),
            score_rows=(),
            memo_rows=(),
            funding_signal=None,
        )
    context = _adjusted_context(request, extracted, institutions)
    stage_a = run_stage_a(context, clock=clock, id_factory=id_factory)
    memo: MemoResult = build_memo(request.memo, llm=llm, clock=clock, id_factory=id_factory)
    return RescoreOutcome(
        status=STATUS_OK,
        run_row=_run_row(request, versions, STATUS_OK, id_factory(), now),
        score_rows=(stage_a.score_row, *stage_a.flipped_rows),
        memo_rows=(memo.memo_row, *memo.flipped_rows),
        funding_signal=interview_funding_signal(extracted),
    )
