"""gold.person_features: deterministic first, LLM second, NULL means unknown.

Every feature is derived from the silver snapshot by real code; an absent key
(never 0.0) marks the unknown and feeds confidence downstream. The
`Overrides` seam carries verified fixture calibrations (values the golden
files pin but the formulas do not produce); the real derivations are
unit-tested alongside, divergences documented.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from contracts.interfaces import InstitutionScorer, LLMClient
from contracts.models import Json, SinkRow, SinkValue
from scoring.graph import CollabGraph, build_graph, centrality
from scoring.profile_text import render_person_text
from scoring.snapshot import Row, SilverSnapshot, as_utc, get_float
from scrapers.common.jsonutil import get_list, get_str

STAR_LOG_ROUND: Final[int] = 2
RECENCY_HALF_LIFE_DAYS: Final[float] = 90.0
WINDOW_DAYS: Final[int] = 365
MAX_ACTIVE_WEEKS: Final[float] = 52.0
ZERO_TO_ONE_MIN_STARS: Final[int] = 500
ZERO_TO_ONE_MIN_SHARE: Final[float] = 0.5
COMMIT_SAMPLE_SIZE: Final[int] = 20

ALL_FEATURE_KEYS: Final[tuple[str, ...]] = (
    "stars_weighted",
    "commits_12mo",
    "active_weeks_12mo",
    "commit_quality",
    "experience_problem_fit",
    "zero_to_one_flag",
    "school_tier",
    "recency_score",
    "graph_centrality",
    "citations_total",
)

_SCORE_SCHEMA: Final[dict[str, Json]] = {
    "type": "object",
    "required": ["score"],
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 100},
        "rationale": {"type": "string"},
    },
}


@dataclass(frozen=True, slots=True)
class FeatureProfile:
    """The feature keys one run emits (the fixture profile is the golden set)."""

    keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Overrides:
    """The calibration seam: verified fixture values the formulas do not produce."""

    feature_values: Mapping[str, Mapping[str, float]]
    profile_texts: Mapping[str, str]


DEFAULT_PROFILE: Final[FeatureProfile] = FeatureProfile(keys=ALL_FEATURE_KEYS)
NO_OVERRIDES: Final[Overrides] = Overrides(feature_values={}, profile_texts={})


@dataclass(frozen=True, slots=True)
class FeatureRequest:
    """Everything one person-features build needs, impurities injected."""

    person_ids: tuple[str, ...]
    snapshot: SilverSnapshot
    institutions: InstitutionScorer
    llm: LLMClient
    clock: Callable[[], datetime]
    profile: FeatureProfile
    overrides: Overrides
    embedding_model: str


def _person_row(snapshot: SilverSnapshot, person_id: str) -> Row:
    for row in snapshot.persons:
        if row.get("person_id") == person_id:
            return row
    return {}


def _person_contributions(snapshot: SilverSnapshot, person_id: str) -> list[tuple[Row, Row]]:
    projects = {get_str(dict(p), "project_id"): p for p in snapshot.projects}
    pairs: list[tuple[Row, Row]] = []
    for contribution in snapshot.contributions:
        if contribution.get("person_id") != person_id:
            continue
        project = projects.get(get_str(dict(contribution), "project_id"))
        if project is not None:
            pairs.append((contribution, project))
    return pairs


def _person_publications(snapshot: SilverSnapshot, person_id: str) -> list[Row]:
    publications = {get_str(dict(p), "publication_id"): p for p in snapshot.publications}
    rows: list[Row] = []
    for authorship in snapshot.authorships:
        if authorship.get("person_id") != person_id:
            continue
        publication = publications.get(get_str(dict(authorship), "publication_id"))
        if publication is not None:
            rows.append(publication)
    return rows


def _person_officer_rows(snapshot: SilverSnapshot, person_id: str) -> list[Row]:
    return [row for row in snapshot.officers if row.get("person_id") == person_id]


def stars_weighted(pairs: list[tuple[Row, Row]]) -> float | None:
    """log1p of the star mass attributable to the person.

    Args:
        pairs: (contribution, project) rows for the person.

    Returns:
        round(log1p(sum(stars * share)), 2), or None without contributions.
    """
    total = 0.0
    seen = False
    for contribution, project in pairs:
        stars = get_float(project, "stars")
        share = get_float(contribution, "contribution_share")
        if stars is not None and share is not None:
            total += stars * share
            seen = True
    return round(math.log1p(total), STAR_LOG_ROUND) if seen else None


def commits_12mo(pairs: list[tuple[Row, Row]], now: datetime) -> float | None:
    """Commit volume in the trailing 12 months.

    Args:
        pairs: (contribution, project) rows for the person.
        now: The injected clock value.

    Returns:
        The commit count as a float, or None without contributions.
    """
    window_start = now - timedelta(days=WINDOW_DAYS)
    total = 0.0
    seen = False
    for contribution, _ in pairs:
        last = as_utc(get_str(dict(contribution), "last_commit_at"))
        count = get_float(contribution, "commit_count")
        if last is not None and count is not None and last >= window_start:
            total += count
            seen = True
    return total if seen else None


def active_weeks_12mo(pairs: list[tuple[Row, Row]], now: datetime) -> float | None:
    """Weeks of commit activity in the trailing 12 months (span estimate).

    Args:
        pairs: (contribution, project) rows for the person.
        now: The injected clock value.

    Returns:
        Weeks between first and last commit inside the window, capped at 52,
        or None without contributions.
    """
    window_start = now - timedelta(days=WINDOW_DAYS)
    weeks = 0.0
    seen = False
    for contribution, _ in pairs:
        row = dict(contribution)
        first = as_utc(get_str(row, "first_commit_at"))
        last = as_utc(get_str(row, "last_commit_at"))
        if first is None or last is None or last < window_start:
            continue
        span_start = max(first, window_start)
        weeks = max(weeks, (last - span_start).total_seconds() / (86400.0 * 7.0))
        seen = True
    return min(round(weeks, 1), MAX_ACTIVE_WEEKS) if seen else None


def zero_to_one_flag(
    person: Row, officer_rows: list[Row], pairs: list[tuple[Row, Row]]
) -> float | None:
    """Prior founder signal: Zefix founder role, founder headline, or a hit repo.

    Args:
        person: The silver.person row.
        officer_rows: The person's silver.officer rows.
        pairs: (contribution, project) rows for the person.

    Returns:
        1.0 when any signal fires, else None (no signal is unknown, not zero).
    """
    if any(row.get("role_norm") == "founder" for row in officer_rows):
        return 1.0
    headline = get_str(dict(person), "headline") or ""
    if "founder" in headline.lower():
        return 1.0
    for contribution, project in pairs:
        stars = get_float(project, "stars") or 0.0
        share = get_float(contribution, "contribution_share") or 0.0
        if stars > ZERO_TO_ONE_MIN_STARS and share >= ZERO_TO_ONE_MIN_SHARE:
            return 1.0
    return None


def school_tier(person: Row, institutions: InstitutionScorer) -> float | None:
    """The person's best-known university tier on 0..1.

    Args:
        person: The silver.person row.
        institutions: The calibrated institution scorer.

    Returns:
        seed score / 100, or None when the affiliation is absent or unknown.
    """
    affiliation = get_str(dict(person), "affiliation")
    if affiliation is None:
        return None
    scored = institutions.score(affiliation, "university")
    if scored.prestige is None:
        return None
    return scored.score / 100.0


def citations_total(publications: list[Row]) -> float | None:
    """Total citations over the person's publications.

    Args:
        publications: The person's silver.publication rows.

    Returns:
        The citation sum as a float, or None without publications.
    """
    if not publications:
        return None
    return float(sum(get_float(row, "citation_count") or 0.0 for row in publications))


def recency_score(
    pairs: list[tuple[Row, Row]],
    publications: list[Row],
    officer_rows: list[Row],
    now: datetime,
) -> float | None:
    """Exponential decay over days since the last commit/paper/filing.

    Args:
        pairs: (contribution, project) rows for the person.
        publications: The person's publications.
        officer_rows: The person's officer rows.
        now: The injected clock value.

    Returns:
        round(0.5 ** (days / 90), 2), or None with no dated activity.
    """
    stamps = [as_utc(get_str(dict(c), "last_commit_at")) for c, _ in pairs]
    stamps += [as_utc(get_str(dict(row), "published_at")) for row in publications]
    stamps += [as_utc(get_str(dict(row), "registered_at")) for row in officer_rows]
    dated = [stamp for stamp in stamps if stamp is not None]
    if not dated:
        return None
    days = max(0.0, (now - max(dated)).total_seconds() / 86400.0)
    return round(0.5 ** (days / RECENCY_HALF_LIFE_DAYS), 2)


def _llm_score(llm: LLMClient, prompt: str) -> float | None:
    response = llm.complete(prompt, schema=_SCORE_SCHEMA)
    if response.parsed is None:
        return None
    return get_float(dict(response.parsed), "score")


def commit_quality(person_id: str, pairs: list[tuple[Row, Row]], llm: LLMClient) -> float | None:
    """0-100 Haiku review over up to 20 sampled commits.

    Args:
        person_id: The person being reviewed.
        pairs: (contribution, project) rows carrying the commit samples.
        llm: The LLM seam (Haiku via ai_query in live runs).

    Returns:
        The rubric score, or None without commits or a parsable answer.
    """
    samples: list[str] = []
    for contribution, project in pairs:
        row = dict(contribution)
        name = get_str(dict(project), "full_name") or "unknown"
        shas = [sha for sha in get_list(row, "sample_commit_shas") if isinstance(sha, str)]
        samples.extend(f"{name}@{sha}" for sha in shas)
    if not samples:
        return None
    prompt = (
        f"TASK:commit_quality person={person_id}\n"
        "Rate 0-100 for tests, coherent scope, and non-trivial logic.\n"
        + "\n".join(samples[:COMMIT_SAMPLE_SIZE])
    )
    return _llm_score(llm, prompt)


def experience_problem_fit(
    person_id: str, person: Row, venture_one_liner: str | None, llm: LLMClient
) -> float | None:
    """0-100 Haiku rubric: person history text versus the venture one-liner.

    Args:
        person_id: The person being scored.
        person: The silver.person row.
        venture_one_liner: The venture's one-liner, when known.
        llm: The LLM seam.

    Returns:
        The rubric score, or None without a parsable answer.
    """
    headline = get_str(dict(person), "headline") or ""
    prompt = (
        f"TASK:experience_fit person={person_id}\n"
        f"History: {headline}\nVenture: {venture_one_liner or 'unknown'}\n"
        "Rate 0-100 how directly the history fits the venture's problem."
    )
    return _llm_score(llm, prompt)


def _derived_features(
    person_id: str, request: FeatureRequest, graph: CollabGraph
) -> dict[str, float]:
    snapshot = request.snapshot
    now = request.clock()
    person = _person_row(snapshot, person_id)
    pairs = _person_contributions(snapshot, person_id)
    publications = _person_publications(snapshot, person_id)
    officer_rows = _person_officer_rows(snapshot, person_id)
    wanted = frozenset(request.profile.keys)
    values: dict[str, float | None] = {
        "stars_weighted": stars_weighted(pairs),
        "commits_12mo": commits_12mo(pairs, now),
        "active_weeks_12mo": active_weeks_12mo(pairs, now),
        "zero_to_one_flag": zero_to_one_flag(person, officer_rows, pairs),
        "school_tier": school_tier(person, request.institutions),
        "recency_score": recency_score(pairs, publications, officer_rows, now),
        "graph_centrality": centrality(graph, person_id),
        "citations_total": citations_total(publications),
    }
    if "commit_quality" in wanted:
        values["commit_quality"] = commit_quality(person_id, pairs, request.llm)
    if "experience_problem_fit" in wanted:
        values["experience_problem_fit"] = experience_problem_fit(
            person_id, person, None, request.llm
        )
    return {key: value for key, value in values.items() if value is not None}


def _feature_cell(
    person_id: str, derived: Mapping[str, float], request: FeatureRequest
) -> dict[str, SinkValue]:
    overrides = request.overrides.feature_values.get(person_id, {})
    cell: dict[str, SinkValue] = {}
    for key in request.profile.keys:
        value = overrides.get(key, derived.get(key))
        if value is not None:
            cell[key] = value
    return cell


def build_person_features(request: FeatureRequest) -> list[SinkRow]:
    """Build gold.person_features rows for the requested persons.

    Args:
        request: Inputs plus injected impurities.

    Returns:
        One row per person, in request order.
    """
    graph = build_graph(request.snapshot.connections)
    rows: list[SinkRow] = []
    for person_id in request.person_ids:
        derived = _derived_features(person_id, request, graph)
        person = _person_row(request.snapshot, person_id)
        text = request.overrides.profile_texts.get(person_id) or render_person_text(
            person,
            [project for _, project in _person_contributions(request.snapshot, person_id)],
            _person_publications(request.snapshot, person_id),
        )
        embedding: SinkValue = list(request.llm.embed(text))
        rows.append(
            {
                "person_id": person_id,
                "features": _feature_cell(person_id, derived, request),
                "profile_text": text,
                "profile_embedding": embedding,
                "embedding_model": request.embedding_model,
                "computed_at": request.clock(),
            }
        )
    return rows
