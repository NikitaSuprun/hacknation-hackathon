# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The ER pipeline: normalize, match, adjudicate, survive - as one pure function.

run_pipeline is side-effect free: rows in, rows out. Composition roots
(er.offline for the credential-free path, er.__main__ for live) own IO. The
one-active-link invariant is asserted before returning; a violation is a bug,
not a data condition.
"""

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from contracts.interfaces import LLMClient
from contracts.models import Json, SinkRow
from er import adjudicate, cluster, connections, normalize, rules, splink_job, survivorship
from er.allocator import PersonIdAllocator
from er.io import RowSource
from er.models import PsrView, ReviewItem, RuleMatch, ScoredPair, psr_view
from scrapers.common.jsonutil import as_sink
from tools.ids import DEALFLOW_NS

Row = dict[str, Json]

STAGE_NORMALIZE: Final[int] = 0
STAGE_DETERMINISTIC: Final[int] = 2
STAGE_SPLINK: Final[int] = 3
STAGE_ADJUDICATE: Final[int] = 4
STAGE_SURVIVORSHIP: Final[int] = 5
ALL_STAGES: Final[frozenset[int]] = frozenset(
    {STAGE_NORMALIZE, STAGE_DETERMINISTIC, STAGE_SPLINK, STAGE_ADJUDICATE, STAGE_SURVIVORSHIP}
)
_MATCHING_STAGES: Final[frozenset[int]] = frozenset(
    {STAGE_DETERMINISTIC, STAGE_SPLINK, STAGE_ADJUDICATE}
)
# A PSR ending every stage unmatched mints a fresh person. The link uses the
# 'seed_fixture' method from the frozen match_method enum (the seeded-person
# marker); a dedicated 'minted' value would be an additive contract change.
MINT_METHOD: Final[str] = "seed_fixture"
MINT_CONFIDENCE: Final[float] = 0.95
MINT_EVIDENCE: Final[Mapping[str, Json]] = {"rule": "fixture seed"}


class LinkInvariantError(AssertionError):
    """A PSR ended the run with a number of active links other than one."""

    def __init__(self, source_record_id: str, count: int) -> None:
        """Name the violating PSR."""
        super().__init__(f"psr {source_record_id} has {count} active links, expected 1")


@dataclass(frozen=True, slots=True)
class ErInputs:
    """Every table the pipeline reads, as parsed rows."""

    github_users: list[Row]
    github_commits: list[Row]
    github_repos: list[Row]
    arxiv_papers: list[Row]
    openalex_works: list[Row]
    zefix_companies: list[Row]
    zefix_sogc: list[Row]
    hacknation_people: list[Row]
    hacknation_projects: list[Row]
    hacknation_cvs: list[Row]
    paper_code_links: list[Row]
    projects: list[Row]
    publications: list[Row]
    companies: list[Row]
    contributions: list[Row]
    authorships: list[Row]
    officers: list[Row]
    psr_rows: list[Row]
    link_rows: list[Row]
    person_rows: list[Row]
    adjudication_rows: list[Row]
    suppression_rows: list[Row]


@dataclass(frozen=True, slots=True)
class ErDeps:
    """The pipeline's injected dependencies."""

    allocator: PersonIdAllocator
    llm: LLMClient
    clock: Callable[[], datetime]
    pipeline_version: str
    deterministic_splink: bool


@dataclass(frozen=True, slots=True)
class ErOutputs:
    """Rows to upsert per table, plus surfaced survivorship conflicts."""

    tables: dict[str, list[SinkRow]]
    conflicts: tuple[survivorship.FieldConflict, ...]


def load_inputs(source: RowSource) -> ErInputs:
    """Read every pipeline input table from one row source.

    Args:
        source: Fixture- or warehouse-backed row source.

    Returns:
        The assembled inputs.
    """
    return ErInputs(
        github_users=source.rows("bronze.github_users_raw"),
        github_commits=source.rows("bronze.github_commits_raw"),
        github_repos=source.rows("bronze.github_repos_raw"),
        arxiv_papers=source.rows("bronze.arxiv_papers_raw"),
        openalex_works=source.rows("bronze.openalex_works_raw"),
        zefix_companies=source.rows("bronze.zefix_companies_raw"),
        zefix_sogc=source.rows("bronze.zefix_sogc_raw"),
        hacknation_people=source.rows("bronze.hacknation_people_raw"),
        hacknation_projects=source.rows("bronze.hacknation_projects_raw"),
        hacknation_cvs=source.rows("bronze.hacknation_cvs_raw"),
        paper_code_links=source.rows("bronze.paper_code_links"),
        projects=source.rows("silver.project"),
        publications=source.rows("silver.publication"),
        companies=source.rows("silver.company"),
        contributions=source.rows("silver.contribution"),
        authorships=source.rows("silver.authorship"),
        officers=source.rows("silver.officer"),
        psr_rows=source.rows("silver.person_source_record"),
        link_rows=source.rows("silver.person_source_link"),
        person_rows=source.rows("silver.person"),
        adjudication_rows=source.rows("ops.llm_adjudications"),
        suppression_rows=source.rows("ops.erasure_suppression"),
    )


def review_id(item: ReviewItem) -> str:
    """Deterministic review-row id, so re-runs MERGE instead of duplicating.

    Args:
        item: The review candidate.

    Returns:
        The UUIDv5 id.
    """
    name = f"er_review:{item.source_record_id}:{item.candidate_person_id}:{item.method}"
    return str(uuid.uuid5(DEALFLOW_NS, name))


@dataclass(slots=True)
class _MatchState:
    """Mutable working state threaded through the matching stages."""

    matches: list[RuleMatch]
    adjudication_rows: list[SinkRow]
    d6_pairs: list[RuleMatch]
    review_pairs: list[tuple[ScoredPair, str, Mapping[str, Json]]]


def run_pipeline(inputs: ErInputs, deps: ErDeps, *, stages: frozenset[int]) -> ErOutputs:
    """Execute the requested stages over the inputs.

    Args:
        inputs: Parsed input tables.
        deps: Injected dependencies.
        stages: Stage numbers to run (0 normalize, 2 deterministic,
            3 splink, 4 adjudication, 5 survivorship/refresh).

    Returns:
        The produced rows per table.
    """
    suppressed = normalize.suppressed_keys(inputs.suppression_rows)
    new_psr_rows: list[SinkRow] = []
    if STAGE_NORMALIZE in stages:
        records = normalize.normalize_bronze(_bronze_tables(inputs), suppressed=suppressed)
        new_psr_rows = [record.to_row() for record in records]
    views: dict[str, PsrView] = {}
    for row in inputs.psr_rows:
        view = psr_view(row)
        views[view.source_record_id] = view
    for sink_row in new_psr_rows:
        view = psr_view(sink_row)
        views[view.source_record_id] = view
    ordered_views = [views[key] for key in sorted(views)]
    linked = _active_links(inputs.link_rows)
    state = _MatchState(matches=[], adjudication_rows=[], d6_pairs=[], review_pairs=[])
    if STAGE_DETERMINISTIC in stages:
        _run_deterministic(inputs, ordered_views, state)
    if STAGE_SPLINK in stages:
        _run_splink(deps, ordered_views, linked, state)
    if STAGE_ADJUDICATE in stages:
        _run_adjudication(inputs, deps, views, state)
    new_links: list[SinkRow] = []
    review_rows: list[SinkRow] = []
    person_of = dict(linked)
    if stages & _MATCHING_STAGES:
        new_links, review_rows = _link_and_mint(deps, ordered_views, linked, person_of, state)
        _assert_one_active_link(views, linked, new_links)
    tables: dict[str, list[SinkRow]] = {
        "silver.person_source_record": new_psr_rows,
        "silver.person_source_link": new_links,
        "ops.llm_adjudications": state.adjudication_rows,
        "ops.er_review_queue": review_rows,
    }
    conflicts: tuple[survivorship.FieldConflict, ...] = ()
    if STAGE_SURVIVORSHIP in stages:
        conflicts = _run_survivorship(inputs, deps, new_psr_rows, person_of, tables)
    return ErOutputs(tables=tables, conflicts=conflicts)


def _active_links(link_rows: list[Row]) -> dict[str, str]:
    linked: dict[str, str] = {}
    for row in link_rows:
        person = row.get("person_id")
        psr = row.get("source_record_id")
        if row.get("status") == "active" and isinstance(person, str) and isinstance(psr, str):
            linked[psr] = person
    return linked


def _bronze_tables(inputs: ErInputs) -> dict[str, list[Row]]:
    return {
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
    }


def _run_deterministic(inputs: ErInputs, ordered_views: list[PsrView], state: _MatchState) -> None:
    crosslinks = rules.build_crosslinks(
        inputs.projects, inputs.publications, inputs.companies, inputs.paper_code_links
    )
    candidates = rules.candidate_pairs(
        crosslinks, inputs.contributions, inputs.authorships, inputs.officers
    )
    for match in rules.deterministic_matches(ordered_views, candidates):
        if match.auto:
            state.matches.append(match)
        else:
            state.d6_pairs.append(match)
    views_by_id = {view.source_record_id: view for view in ordered_views}
    d8_candidates = rules.hacknation_repo_candidates(
        inputs.hacknation_projects, inputs.projects, inputs.contributions
    )
    state.matches.extend(rules.hacknation_matches(views_by_id, d8_candidates))


def _same_component(matches: list[RuleMatch]) -> Callable[[str, str], bool]:
    """Membership test over the components of the current auto matches."""
    component_of: dict[str, frozenset[str]] = {}
    for component in cluster.components(matches):
        for member in component:
            component_of[member] = component

    def connected(left: str, right: str) -> bool:
        return right in component_of.get(left, frozenset())

    return connected


def _run_splink(
    deps: ErDeps,
    ordered_views: list[PsrView],
    linked: Mapping[str, str],
    state: _MatchState,
) -> None:
    scored = splink_job.score_pairs(ordered_views, train=not deps.deterministic_splink)
    already_matched = _same_component(state.matches)
    for pair in splink_job.filter_unlinked_pairs(scored, frozenset(linked)):
        if already_matched(pair.left, pair.right):
            continue
        band = splink_job.band_of(pair.probability)
        if band == "auto":
            state.matches.append(
                RuleMatch(
                    left=pair.left,
                    right=pair.right,
                    rule="splink",
                    method="splink",
                    confidence=round(pair.probability, 2),
                    auto=True,
                    evidence=pair.comparison,
                )
            )
        elif band == "adjudicate":
            state.review_pairs.append((pair, "adjudicate", pair.comparison))
        elif band == "review":
            state.review_pairs.append(
                (pair, "splink", splink_job.features_from_vector(dict(pair.comparison)))
            )


def _run_adjudication(
    inputs: ErInputs,
    deps: ErDeps,
    views: Mapping[str, PsrView],
    state: _MatchState,
) -> None:
    band_pairs = [pair for pair, kind, _ in state.review_pairs if kind == "adjudicate"]
    settled = adjudicate.settled_pair_ids(inputs.adjudication_rows)
    verdicts = adjudicate.adjudicate_pairs(
        band_pairs,
        views,
        deps.llm,
        existing_pair_ids=settled,
        clock=deps.clock,
        pipeline_version=deps.pipeline_version,
    )
    state.review_pairs = [entry for entry in state.review_pairs if entry[1] != "adjudicate"]
    for verdict in verdicts:
        state.adjudication_rows.append(verdict.row)
        if verdict.verdict == "match":
            state.matches.append(
                RuleMatch(
                    left=verdict.left,
                    right=verdict.right,
                    rule="llm",
                    method="llm_adjudication",
                    confidence=adjudicate.LLM_LINK_CONFIDENCE,
                    auto=True,
                    evidence=verdict.evidence,
                )
            )
        elif verdict.verdict == "unsure":
            pair = ScoredPair(
                left=verdict.left,
                right=verdict.right,
                probability=verdict.probability,
                comparison=verdict.evidence,
            )
            state.review_pairs.append((pair, "llm_adjudication", verdict.evidence))


def _link_and_mint(
    deps: ErDeps,
    ordered_views: list[PsrView],
    linked: Mapping[str, str],
    person_of: dict[str, str],
    state: _MatchState,
) -> tuple[list[SinkRow], list[SinkRow]]:
    """Cluster the auto matches, link, mint singletons, and shape review rows."""
    now = deps.clock()
    usable = [
        match for match in state.matches if not (match.left in linked and match.right in linked)
    ]
    guard = cluster.guard_same_source(
        cluster.components(usable), {view.source_record_id: view.source for view in ordered_views}
    )
    new_links = cluster.build_links(
        guard.clusters,
        usable,
        deps.allocator,
        linked=linked,
        clock=deps.clock,
        pipeline_version=deps.pipeline_version,
    )
    anchored = set(linked)
    for link in new_links:
        psr = str(link["source_record_id"])
        person_of[psr] = str(link["person_id"])
        anchored.add(psr)
    for view in ordered_views:
        if view.source_record_id in person_of:
            continue
        person = deps.allocator.allocate(frozenset({view.source_record_id}))
        new_links.append(
            cluster.link_row(
                person,
                view.source_record_id,
                method=MINT_METHOD,
                confidence=MINT_CONFIDENCE,
                evidence=MINT_EVIDENCE,
                matched_at=now,
                pipeline_version=deps.pipeline_version,
            )
        )
        person_of[view.source_record_id] = person
    review_rows = _review_rows(person_of, frozenset(anchored), guard, state, now)
    return new_links, review_rows


def _review_rows(
    person_of: Mapping[str, str],
    anchored: frozenset[str],
    guard: cluster.ClusterResult,
    state: _MatchState,
    now: datetime,
) -> list[SinkRow]:
    items: list[ReviewItem] = []
    for match in state.d6_pairs:
        item = _pair_review_item(
            match.left,
            match.right,
            person_of,
            anchored,
            score=match.confidence,
            method="det_name_org",
            features=dict(match.evidence),
        )
        if item is not None:
            items.append(item)
    for pair, kind, features in state.review_pairs:
        item = _pair_review_item(
            pair.left,
            pair.right,
            person_of,
            anchored,
            score=round(pair.probability, 4),
            method=kind,
            features=dict(features),
        )
        if item is not None:
            items.append(item)
    for ejection in guard.ejected:
        ejected_item = cluster.review_item_from_ejection(ejection, person_of)
        if ejected_item is not None:
            items.append(ejected_item)
    best: dict[tuple[str, str], ReviewItem] = {}
    for item in items:
        key = (item.source_record_id, item.candidate_person_id)
        current = best.get(key)
        if current is None or item.score > current.score:
            best[key] = item
    return [
        {
            "review_id": review_id(item),
            "source_record_id": item.source_record_id,
            "candidate_person_id": item.candidate_person_id,
            "score": item.score,
            "method": item.method,
            "features": as_sink(dict(item.features)),
            "status": "pending",
            "decided_by": None,
            "decided_at": None,
            "created_at": now,
        }
        for _, item in sorted(best.items())
    ]


def _pair_review_item(  # noqa: PLR0913 - a review row's full decision surface
    left: str,
    right: str,
    person_of: Mapping[str, str],
    anchored: frozenset[str],
    *,
    score: float,
    method: str,
    features: dict[str, Json],
) -> ReviewItem | None:
    """One review row per still-separate pair: the newcomer versus the candidate.

    The subject is the pair member that was neither pre-linked nor matched
    this run (the newcomer); pairs that ended up on one person need no review.
    """
    person_left = person_of.get(left)
    person_right = person_of.get(right)
    if person_left is None or person_right is None or person_left == person_right:
        return None
    if left not in anchored:
        subject, candidate = left, person_right
    elif right not in anchored:
        subject, candidate = right, person_left
    else:
        subject, candidate = min((left, person_right), (right, person_left))
    return ReviewItem(
        source_record_id=subject,
        candidate_person_id=candidate,
        score=score,
        method=method,
        features=features,
    )


def _assert_one_active_link(
    views: Mapping[str, PsrView], linked: Mapping[str, str], new_links: list[SinkRow]
) -> None:
    """Raise LinkInvariantError unless every PSR ends with exactly one link."""
    counts: dict[str, int] = dict.fromkeys(views, 0)
    for psr in linked:
        if psr in counts:
            counts[psr] += 1
    for link in new_links:
        psr = str(link["source_record_id"])
        if psr in counts:
            counts[psr] += 1
    for psr, count in sorted(counts.items()):
        if count != 1:
            raise LinkInvariantError(psr, count)


def _run_survivorship(
    inputs: ErInputs,
    deps: ErDeps,
    new_psr_rows: list[SinkRow],
    person_of: Mapping[str, str],
    tables: dict[str, list[SinkRow]],
) -> tuple[survivorship.FieldConflict, ...]:
    known = {str(row.get("source_record_id")) for row in inputs.psr_rows}
    all_rows: list[Row] = list(inputs.psr_rows)
    all_rows.extend(
        _as_json_row(sink_row)
        for sink_row in new_psr_rows
        if str(sink_row.get("source_record_id")) not in known
    )
    persons, conflicts = survivorship.build_persons(
        all_rows,
        person_of,
        llm=deps.llm,
        clock=deps.clock,
        bronze_users=inputs.github_users,
        hacknation_projects=inputs.hacknation_projects,
        existing_persons=inputs.person_rows,
    )
    tables["silver.person"] = persons
    tables["silver.contribution"] = survivorship.backfill_person_id(inputs.contributions, person_of)
    tables["silver.authorship"] = survivorship.backfill_person_id(inputs.authorships, person_of)
    tables["silver.officer"] = survivorship.backfill_person_id(inputs.officers, person_of)
    tables["silver.person_connection"] = connections.build_connections(
        inputs.authorships,
        inputs.contributions,
        inputs.officers,
        inputs.publications,
        person_of,
        clock=deps.clock,
    )
    return tuple(conflicts)


def _as_json_row(sink_row: SinkRow) -> Row:
    """Bridge a freshly normalized PSR row into the JSON row shape."""
    bridged: Row = {}
    for key, value in sink_row.items():
        if isinstance(value, datetime):
            bridged[key] = value.isoformat()
        elif isinstance(value, list):
            bridged[key] = [str(item) for item in value]
        elif value is None or isinstance(value, str | int | float | bool):
            bridged[key] = value
    return bridged
