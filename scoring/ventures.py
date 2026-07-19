# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Venture construction: resolved silver anchors into gold.venture(+members).

Repo anchors pass the venture-likeness gate, companies pass the startup gate,
and anchors merge when they share golden persons plus a cross-reference
(homepage equals the company website, the company is named in the repo text,
or the Zefix purpose fuzzy-matches the repo name). The merged venture keeps a
deterministic id from its earliest-seen anchor, and lifecycle fields pass
through from prior gold rows so re-running the job is a fixed point.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final

from rapidfuzz import fuzz

from contracts.interfaces import LLMClient
from contracts.models import Json, SinkRow
from er.normalize import HACKNATION_SOURCE, hacknation_member_entries, hacknation_user_id
from scoring.snapshot import Row, SilverSnapshot, get_bool, get_float, require_str
from scrapers.common.jsonutil import as_sink, get_list, get_map, get_str
from tools import ids
from tools.norm import url_norm

VENTURE_LIKENESS_MIN: Final[float] = 0.6
CORE_SHARE_MIN: Final[float] = 0.10
SECONDARY_SHARE_MIN: Final[float] = 0.05
SECONDARY_COMMITS_MIN: Final[float] = 10.0
MAX_MEMBERS: Final[int] = 8
BOARD_WEIGHT_FACTOR: Final[float] = 0.5
FUZZY_MERGE_MIN: Final[float] = 0.85
MERGE_SHARED_PERSONS: Final[int] = 2
WEIGHT_ROUND: Final[int] = 4

STATUS_SOURCED: Final[str] = "sourced"
STARTUP_LIKENESS_GATE: Final[str] = "tech_startup_candidate"
ANCHOR_HACKATHON: Final[str] = "hackathon_project"

REPO_NOISE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"awesome-|course|tutorial|exercise|dotfiles|\bbook\b|\bdemo\b|\bmeme\b", re.IGNORECASE
)
RESEARCH_HINT_PATTERN: Final[re.Pattern[str]] = re.compile(r"arxiv|paper", re.IGNORECASE)

LEGAL_SUFFIXES: Final[frozenset[str]] = frozenset(
    {"ag", "gmbh", "sa", "sarl", "inc", "llc", "ltd", "se", "kg", "co", "corp", "plc"}
)

NOISE_LIKENESS: Final[float] = 0.2
BASE_LIKENESS: Final[float] = 0.5
DESCRIPTION_BONUS: Final[float] = 0.1
RESEARCH_BONUS: Final[float] = 0.15


def classify_repo_likeness(name: str, description: str | None, readme: str | None) -> float:
    """Heuristic venture-likeness for a repo (higher = more venture-shaped).

    Directional only: awesome-lists, courses, dotfiles, and demo/book/meme
    repos land clearly below real product repos; exact values are not part of
    the contract (silver carries the classifier output).

    Args:
        name: Repo name.
        description: Repo description, when present.
        readme: README text, when present.

    Returns:
        A 0..1 likeness estimate.
    """
    haystack = " ".join(part for part in (name, description) if part)
    if REPO_NOISE_PATTERN.search(haystack):
        return NOISE_LIKENESS
    likeness = BASE_LIKENESS
    if description:
        likeness += DESCRIPTION_BONUS
    if readme and RESEARCH_HINT_PATTERN.search(readme):
        likeness += RESEARCH_BONUS
    return round(min(likeness, 1.0), 2)


@dataclass(frozen=True, slots=True)
class MemberSeed:
    """One venture member before rendering: identity, weight, and evidence."""

    person_id: str
    weight: float
    role_hint: str
    is_founder_guess: bool
    evidence: dict[str, Json]


@dataclass(frozen=True, slots=True)
class VentureBuild:
    """The venture rows plus member rows one build produces."""

    venture_rows: list[SinkRow]
    member_rows: list[SinkRow]


def strip_legal_suffix(name: str) -> str:
    """Company display name without trailing legal-form tokens.

    Args:
        name: The registered company name.

    Returns:
        The name minus trailing legal suffixes ('GraspLab AG' -> 'GraspLab').
    """
    tokens = name.split()
    while tokens and tokens[-1].lower() in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens) or name


def _repo_members(snapshot: SilverSnapshot, project_id: str) -> list[MemberSeed]:
    rows = [
        row
        for row in snapshot.contributions
        if row.get("project_id") == project_id and get_str(dict(row), "person_id") is not None
    ]
    kept: list[tuple[str, float]] = []
    for row in rows:
        share = get_float(row, "contribution_share") or 0.0
        commits = get_float(row, "commit_count") or 0.0
        if share >= CORE_SHARE_MIN or (
            share >= SECONDARY_SHARE_MIN and commits >= SECONDARY_COMMITS_MIN
        ):
            kept.append((require_str(row, "person_id"), share))
    kept.sort(key=lambda item: item[1], reverse=True)
    kept = kept[:MAX_MEMBERS]
    total = sum(share for _, share in kept)
    seeds: list[MemberSeed] = []
    for person_id, share in kept:
        weight = round(share / total, WEIGHT_ROUND) if total > 0 else 0.0
        seeds.append(
            MemberSeed(
                person_id=person_id,
                weight=weight,
                role_hint="maintainer",
                is_founder_guess=False,
                evidence={"contribution_share": share},
            )
        )
    return seeds


def _officer_members(snapshot: SilverSnapshot, company_id: str) -> list[MemberSeed]:
    seeds: list[MemberSeed] = []
    for row in snapshot.officers:
        if row.get("company_id") != company_id:
            continue
        mapping = dict(row)
        person_id = get_str(mapping, "person_id")
        if person_id is None or get_str(mapping, "signing_authority") is None:
            continue
        role_norm = get_str(mapping, "role_norm") or "officer"
        weight = BOARD_WEIGHT_FACTOR if role_norm == "board" else 1.0
        seeds.append(
            MemberSeed(
                person_id=person_id,
                weight=weight,
                role_hint="founder" if role_norm == "founder" else "officer",
                is_founder_guess=role_norm == "founder",
                evidence={"officer_role": role_norm},
            )
        )
    return seeds


def _cross_referenced(project: Row, company: Row) -> bool:
    project_map = dict(project)
    company_map = dict(company)
    homepage = get_str(project_map, "homepage_url")
    website = get_str(company_map, "website_url")
    if homepage and website and url_norm(homepage) == url_norm(website):
        return True
    company_name = get_str(company_map, "name")
    description = (get_str(project_map, "description") or "").lower()
    if company_name and strip_legal_suffix(company_name).lower() in description:
        return True
    purpose = get_str(company_map, "purpose") or ""
    repo_name = get_str(project_map, "name") or ""
    if purpose and repo_name:
        ratio = fuzz.partial_ratio(purpose.lower(), repo_name.lower()) / 100.0
        return ratio >= FUZZY_MERGE_MIN
    return False


def _merges(
    project: Row, company: Row, repo_seeds: list[MemberSeed], officer_seeds: list[MemberSeed]
) -> bool:
    shared = {seed.person_id for seed in repo_seeds} & {seed.person_id for seed in officer_seeds}
    if len(shared) >= MERGE_SHARED_PERSONS:
        return True
    return len(shared) >= 1 and _cross_referenced(project, company)


def _merge_members(
    repo_seeds: list[MemberSeed], officer_seeds: list[MemberSeed]
) -> list[MemberSeed]:
    by_person = {seed.person_id: seed for seed in repo_seeds}
    merged: list[MemberSeed] = []
    appended: list[MemberSeed] = []
    for officer in officer_seeds:
        existing = by_person.get(officer.person_id)
        if existing is None:
            appended.append(officer)
            continue
        evidence = dict(existing.evidence)
        evidence.update(officer.evidence)
        by_person[officer.person_id] = MemberSeed(
            person_id=existing.person_id,
            weight=existing.weight,
            role_hint=officer.role_hint if officer.is_founder_guess else existing.role_hint,
            is_founder_guess=existing.is_founder_guess or officer.is_founder_guess,
            evidence=evidence,
        )
    merged = list(by_person.values())
    if appended:
        total = sum(seed.weight for seed in merged) + sum(seed.weight for seed in appended)
        if total > 0:
            merged = [
                MemberSeed(
                    person_id=seed.person_id,
                    weight=round(seed.weight / total, WEIGHT_ROUND),
                    role_hint=seed.role_hint,
                    is_founder_guess=seed.is_founder_guess,
                    evidence=seed.evidence,
                )
                for seed in (*merged, *appended)
            ]
    merged.sort(key=lambda seed: seed.weight, reverse=True)
    return merged[:MAX_MEMBERS]


@dataclass(frozen=True, slots=True)
class _Anchor:
    """One venture-to-be: anchor identity plus its display fields."""

    venture_id: str
    anchor_type: str
    anchor_id: str
    name: str
    one_liner: str | None
    market_tags: tuple[str, ...]
    website_url: str | None
    members: tuple[MemberSeed, ...]


def _repo_anchor(snapshot: SilverSnapshot, project: Row) -> _Anchor:
    project_map = dict(project)
    project_id = require_str(project, "project_id")
    company = _matching_company(snapshot, project)
    name = get_str(project_map, "name") or project_id
    members = _repo_members(snapshot, project_id)
    if company is not None:
        company_map = dict(company)
        name = strip_legal_suffix(get_str(company_map, "name") or name)
        members = _merge_members(
            members, _officer_members(snapshot, require_str(company, "company_id"))
        )
    tags = tuple(tag for tag in get_list(project_map, "market_tags") if isinstance(tag, str))
    return _Anchor(
        venture_id=ids.venture_id("repo", project_id),
        anchor_type="repo",
        anchor_id=project_id,
        name=name,
        one_liner=get_str(project_map, "description"),
        market_tags=tags,
        website_url=get_str(project_map, "homepage_url")
        or (get_str(dict(company), "website_url") if company is not None else None),
        members=tuple(members),
    )


def _matching_company(snapshot: SilverSnapshot, project: Row) -> Row | None:
    project_id = require_str(project, "project_id")
    repo_seeds = _repo_members(snapshot, project_id)
    for company in snapshot.companies:
        officer_seeds = _officer_members(snapshot, require_str(company, "company_id"))
        if officer_seeds and _merges(project, company, repo_seeds, officer_seeds):
            return company
    return None


def _company_anchor(snapshot: SilverSnapshot, company: Row) -> _Anchor:
    company_map = dict(company)
    company_id = require_str(company, "company_id")
    name = get_str(company_map, "name") or company_id
    return _Anchor(
        venture_id=ids.venture_id("company", company_id),
        anchor_type="company",
        anchor_id=company_id,
        name=strip_legal_suffix(name),
        one_liner=get_str(company_map, "purpose"),
        market_tags=(),
        website_url=get_str(company_map, "website_url"),
        members=tuple(_officer_members(snapshot, company_id)),
    )


def _merged_company_ids(snapshot: SilverSnapshot, projects: list[Row]) -> set[str]:
    consumed: set[str] = set()
    for project in projects:
        company = _matching_company(snapshot, project)
        if company is not None:
            consumed.add(require_str(company, "company_id"))
    return consumed


def _gated_projects(snapshot: SilverSnapshot) -> list[Row]:
    kept: list[Row] = []
    for project in snapshot.projects:
        likeness = get_float(project, "venture_likeness") or 0.0
        if likeness >= VENTURE_LIKENESS_MIN and get_bool(project, "is_corporate_oss") is not True:
            kept.append(project)
    return kept


def _active_person_links(snapshot: SilverSnapshot) -> dict[str, str]:
    """source_record_id to person_id over the active ER links."""
    linked: dict[str, str] = {}
    for row in snapshot.person_links:
        mapping = dict(row)
        psr = get_str(mapping, "source_record_id")
        person = get_str(mapping, "person_id")
        if row.get("status") == "active" and psr is not None and person is not None:
            linked[psr] = person
    return linked


def _hackathon_members(payload: dict[str, Json], person_of: Mapping[str, str]) -> list[MemberSeed]:
    """Author + team[] as member seeds; only ER-resolved persons qualify."""
    author_id = hacknation_user_id(get_map(payload, "authorProfile"))
    picked: list[tuple[str, str | None, bool]] = []
    seen: set[str] = set()
    for entry in hacknation_member_entries(payload):
        user_id = hacknation_user_id(entry)
        person = (
            person_of.get(ids.psr_id(HACKNATION_SOURCE, user_id)) if user_id is not None else None
        )
        if person is None or person in seen:
            continue
        seen.add(person)
        picked.append((person, get_str(entry, "role"), user_id == author_id))
    weight = round(1.0 / len(picked), WEIGHT_ROUND) if picked else 0.0
    return [
        MemberSeed(
            person_id=person,
            weight=weight,
            role_hint="founder" if is_author else (role or "member"),
            is_founder_guess=is_author,
            evidence={
                "source": HACKNATION_SOURCE,
                "role": "author" if is_author else (role or "member"),
            },
        )
        for person, role, is_author in picked
    ]


def _hackathon_anchor(row: Row, members: list[MemberSeed]) -> _Anchor:
    """One venture anchor from a Hack Nation project detail payload."""
    payload = get_map(dict(row), "payload")
    # The anchor is the silver.project row scrapers.hacknation.silver derives
    # from this payload, so it carries that derived id and the same fields:
    # market_tags are the pitch tags, while techStack lands in topics there.
    project_id = ids.hacknation_project_id(require_str(row, "project_id"))
    return _Anchor(
        venture_id=ids.venture_id(ANCHOR_HACKATHON, project_id),
        anchor_type=ANCHOR_HACKATHON,
        anchor_id=project_id,
        name=get_str(payload, "title") or project_id,
        one_liner=get_str(payload, "summary"),
        market_tags=tuple(tag for tag in get_list(payload, "tags") if isinstance(tag, str)),
        # A pitched repo is the storefront when the project ships no demo.
        website_url=get_str(payload, "demoUrl") or get_str(payload, "githubUrl"),
        members=tuple(members),
    )


def _hackathon_citation(seed: MemberSeed, hn_project_id: str) -> dict[str, Json]:
    """The pitch provenance one repo member picks up: authorship or team role."""
    if seed.is_founder_guess:
        return {"hacknation_author": hn_project_id}
    return {"hacknation_role": seed.role_hint}


def _absorb_hackathon_members(
    anchor: _Anchor, members: list[MemberSeed], hn_project_id: str
) -> _Anchor:
    """Auto-merge on githubUrl: the repo anchor wins, cited by the pitch.

    Repo member rows stay byte-stable (weights and role hints untouched) so a
    merge cannot reshuffle an already-scored venture; a person on both sides
    keeps the repo seed with the pitch citation folded into its evidence, and
    only persons the repo does not already carry append. The shared-persons
    merge remains the backstop for everything else.
    """
    pitched = {seed.person_id: seed for seed in members}
    existing = {seed.person_id for seed in anchor.members}
    kept: list[MemberSeed] = []
    for seed in anchor.members:
        pitch = pitched.get(seed.person_id)
        if pitch is None:
            kept.append(seed)
            continue
        citation = _hackathon_citation(pitch, hn_project_id)
        kept.append(replace(seed, evidence=seed.evidence | citation))
    fresh = [seed for seed in members if seed.person_id not in existing]
    return replace(anchor, members=(*kept, *fresh))


def _repo_anchor_urls(projects: list[Row]) -> dict[str, str]:
    """Normalized github.com/{full_name} URL to project_id for repo anchors."""
    by_url: dict[str, str] = {}
    for project in projects:
        mapping = dict(project)
        full_name = get_str(mapping, "full_name")
        project_id = get_str(mapping, "project_id")
        if full_name is None or project_id is None:
            continue
        url = url_norm(f"github.com/{full_name}")
        if url is not None:
            by_url.setdefault(url, project_id)
    return by_url


def _extend_with_hackathon(
    snapshot: SilverSnapshot, anchors: list[_Anchor], gated_projects: list[Row]
) -> None:
    """Merge or append one anchor per Hack Nation project (githubUrl merge)."""
    person_of = _active_person_links(snapshot)
    url_to_project = _repo_anchor_urls(gated_projects)
    index_by_project = {
        anchor.anchor_id: index
        for index, anchor in enumerate(anchors)
        if anchor.anchor_type == "repo"
    }
    ordered = sorted(snapshot.hacknation_projects, key=lambda row: str(row.get("project_id")))
    for row in ordered:
        hn_project_id = require_str(row, "project_id")
        payload = get_map(dict(row), "payload")
        members = _hackathon_members(payload, person_of)
        github_url = get_str(payload, "githubUrl")
        repo_url = url_norm(github_url) if github_url is not None else None
        target_project = url_to_project.get(repo_url) if repo_url is not None else None
        target = index_by_project.get(target_project) if target_project is not None else None
        if target is not None:
            anchors[target] = _absorb_hackathon_members(anchors[target], members, hn_project_id)
        else:
            anchors.append(_hackathon_anchor(row, members))


def _member_universities(payload: dict[str, Json]) -> list[Json]:
    """Distinct member universities, first-seen order."""
    seen: dict[str, None] = {}
    for entry in hacknation_member_entries(payload):
        university = get_str(entry, "university")
        if university is not None:
            seen.setdefault(university, None)
    return list(seen)


def hackathon_extras(snapshot: SilverSnapshot, venture_row: Row) -> dict[str, Json]:
    """Scoring extras for a hackathon_project venture (structured pitch + signal).

    Args:
        snapshot: The silver snapshot (bronze.hacknation_projects_raw rows).
        venture_row: The gold.venture row being scored.

    Returns:
        The pitch/hackathon extras; empty for non-hackathon anchors or when
        the anchor project is absent from the snapshot.
    """
    if venture_row.get("anchor_type") != ANCHOR_HACKATHON:
        return {}
    anchor_id = get_str(dict(venture_row), "anchor_id")
    for row in snapshot.hacknation_projects:
        # The anchor is a derived silver.project id; bronze stays keyed by the
        # Hack Nation project key the detail payload was fetched under.
        project_key = get_str(dict(row), "project_id")
        if project_key is None or ids.hacknation_project_id(project_key) != anchor_id:
            continue
        payload = get_map(dict(row), "payload")
        return {
            "structured": payload.get("structured"),
            "event_title": get_str(payload, "eventTitle"),
            "challenge_title": get_str(payload, "challengeTitle"),
            "winner": payload.get("winner"),
            "tech_stack": payload.get("techStack"),
            "universities": _member_universities(payload),
            "github_url": get_str(payload, "githubUrl"),
        }
    return {}


def _venture_row(anchor: _Anchor, prior: Row | None, summary: str | None, now: datetime) -> SinkRow:
    market_tags: list[Json] = list(anchor.market_tags)
    return {
        "venture_id": anchor.venture_id,
        "anchor_type": anchor.anchor_type,
        "anchor_id": anchor.anchor_id,
        "name": anchor.name,
        "one_liner": anchor.one_liner,
        "summary_ai": summary,
        "market_tags": as_sink(market_tags),
        "website_url": anchor.website_url,
        "quality_tier": as_sink(prior.get("quality_tier")) if prior is not None else None,
        "status": as_sink(prior.get("status")) if prior is not None else STATUS_SOURCED,
        "created_at": as_sink(prior.get("created_at")) if prior is not None else now,
        "updated_at": now,
    }


def _member_rows(anchor: _Anchor, now: datetime) -> list[SinkRow]:
    return [
        {
            "venture_id": anchor.venture_id,
            "person_id": seed.person_id,
            "role_hint": seed.role_hint,
            "is_founder_guess": seed.is_founder_guess,
            "weight": seed.weight,
            "evidence": as_sink(dict(seed.evidence)),
            "added_by": "pipeline",
            "added_at": now,
        }
        for seed in anchor.members
    ]


def build_ventures(
    snapshot: SilverSnapshot,
    prior_ventures: tuple[Row, ...],
    llm: LLMClient,
    clock: Callable[[], datetime],
) -> VentureBuild:
    """Build gold.venture and gold.venture_member rows from the snapshot.

    Args:
        snapshot: The silver snapshot.
        prior_ventures: Existing gold.venture rows (lifecycle passthrough).
        llm: Summary generation seam (TASK:venture_summary prompts).
        clock: Injected time source.

    Returns:
        The venture and member rows, members ordered by weight.
    """
    now = clock()
    prior_by_id = {get_str(dict(row), "venture_id"): row for row in prior_ventures}
    projects = _gated_projects(snapshot)
    consumed = _merged_company_ids(snapshot, projects)
    anchors = [_repo_anchor(snapshot, project) for project in projects]
    for company in snapshot.companies:
        company_id = require_str(company, "company_id")
        likeness = get_str(dict(company), "startup_likeness")
        if company_id not in consumed and likeness == STARTUP_LIKENESS_GATE:
            anchors.append(_company_anchor(snapshot, company))
    _extend_with_hackathon(snapshot, anchors, projects)
    venture_rows: list[SinkRow] = []
    member_rows: list[SinkRow] = []
    for anchor in anchors:
        summary = llm.complete(
            f"TASK:venture_summary venture={anchor.venture_id}\n"
            f"{anchor.name}: {anchor.one_liner or ''}\n"
            "Summarize this venture in one sentence."
        ).text
        venture_rows.append(_venture_row(anchor, prior_by_id.get(anchor.venture_id), summary, now))
        member_rows.extend(_member_rows(anchor, now))
    return VentureBuild(venture_rows=venture_rows, member_rows=member_rows)
