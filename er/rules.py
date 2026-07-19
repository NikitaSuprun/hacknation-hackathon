# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Stages 1-2: artifact cross-links and the deterministic match rules D1-D8.

Stage 1 links artifacts (repo<->paper<->company) through high-precision signals
observed in the artifacts themselves; each linked pair generates candidate
person pairs (top contributors x authors/officers). Stage 2 then matches PSR
pairs on independent identifiers; name-plus-org alone (D6) never auto-links.
D7 matches LinkedIn URLs across sources; D8 pairs Hack Nation project members
with the core contributors of the repo their project's githubUrl names.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from rapidfuzz.distance import JaroWinkler

from contracts.models import Json
from er.models import PsrView, RuleMatch
from er.normalize import HACKNATION_SOURCE, hacknation_member_entries, hacknation_user_id
from scrapers.common.jsonutil import get_list, get_map, get_str
from tools import ids, norm

Row = dict[str, Json]

TOP_CONTRIBUTOR_SHARE: Final[float] = 0.5
NAME_JW_THRESHOLD: Final[float] = 0.92
NAME_JW_D8: Final[float] = 0.90

_CONF_ORCID: Final[float] = 0.99
_CONF_EMAIL: Final[float] = 0.98
_CONF_WEBSITE: Final[float] = 0.95
_CONF_HANDLE: Final[float] = 0.95
_CONF_LINKEDIN: Final[float] = 0.97
_CONF_CROSSLINK: Final[float] = 0.92
_CONF_GITHUB_CONTRIB: Final[float] = 0.90
_CONF_NAME_ORG: Final[float] = 0.85


@dataclass(frozen=True, slots=True)
class CrossLinks:
    """Artifact-level links: each pair carries a stable evidence description."""

    project_publications: Mapping[tuple[str, str], str]
    project_companies: Mapping[tuple[str, str], str]


def _github_repo_urls(full_name: str) -> set[str]:
    normalized = norm.url_norm(f"github.com/{full_name}")
    return {normalized} if normalized is not None else set()


def build_crosslinks(
    projects: Sequence[Row],
    publications: Sequence[Row],
    companies: Sequence[Row],
    paper_code_links: Sequence[Row],
) -> CrossLinks:
    """Derive repo<->paper and repo<->company links from artifact signals.

    Args:
        projects: silver.project rows.
        publications: silver.publication rows.
        companies: silver.company rows.
        paper_code_links: bronze.paper_code_links rows (PwC archive).

    Returns:
        The artifact cross-links with per-pair descriptions.
    """
    by_arxiv: dict[str, str] = {}
    pub_names: dict[str, str] = {}
    for publication in publications:
        pub_id = get_str(publication, "publication_id")
        arxiv_id = get_str(publication, "arxiv_id")
        if pub_id is None:
            continue
        pub_names[pub_id] = arxiv_id or pub_id
        if arxiv_id is not None:
            by_arxiv[arxiv_id] = pub_id
    archive_arxiv_by_repo: dict[str, str] = {}
    for link in paper_code_links:
        repo_url = get_str(link, "repo_url")
        arxiv_id = get_str(link, "paper_arxiv_id")
        if repo_url is not None and arxiv_id is not None:
            normalized = norm.url_norm(repo_url)
            if normalized is not None:
                archive_arxiv_by_repo[normalized] = arxiv_id
    project_publications: dict[tuple[str, str], str] = {}
    project_companies: dict[tuple[str, str], str] = {}
    code_urls_by_pub = {
        pub_id: {
            u
            for raw in get_list(publication, "code_urls")
            if isinstance(raw, str) and (u := norm.url_norm(raw)) is not None
        }
        for publication in publications
        if (pub_id := get_str(publication, "publication_id")) is not None
    }
    for project in projects:
        _link_project(
            project,
            by_arxiv,
            pub_names,
            archive_arxiv_by_repo,
            code_urls_by_pub,
            project_publications,
        )
        _link_company(project, companies, project_companies)
    return CrossLinks(
        project_publications=project_publications, project_companies=project_companies
    )


def _link_project(  # noqa: PLR0913 - the stage-1 lookup tables are irreducible
    project: Row,
    by_arxiv: Mapping[str, str],
    pub_names: Mapping[str, str],
    archive_arxiv_by_repo: Mapping[str, str],
    code_urls_by_pub: Mapping[str, set[str]],
    out: dict[tuple[str, str], str],
) -> None:
    """Collect every publication link of one project into `out`."""
    project_id = get_str(project, "project_id")
    full_name = get_str(project, "full_name")
    if project_id is None or full_name is None:
        return
    repo_urls = _github_repo_urls(full_name)
    linked: dict[str, str] = {}
    for raw in get_list(project, "arxiv_ids_in_readme"):
        if isinstance(raw, str) and raw in by_arxiv:
            linked.setdefault(by_arxiv[raw], f"arxiv:{raw} in {full_name} readme")
    for pub_id, urls in code_urls_by_pub.items():
        if urls & repo_urls:
            linked.setdefault(pub_id, f"{full_name} in code_urls of {pub_names[pub_id]}")
    for repo_url in repo_urls:
        arxiv_id = archive_arxiv_by_repo.get(repo_url)
        if arxiv_id is not None and arxiv_id in by_arxiv:
            linked.setdefault(by_arxiv[arxiv_id], f"paper_code_links {full_name} x {arxiv_id}")
    for pub_id, description in linked.items():
        out[(project_id, pub_id)] = description


def _link_company(project: Row, companies: Sequence[Row], out: dict[tuple[str, str], str]) -> None:
    """Collect homepage/company-website matches of one project into `out`."""
    project_id = get_str(project, "project_id")
    homepage = get_str(project, "homepage_url")
    if project_id is None or homepage is None:
        return
    homepage_norm = norm.url_norm(homepage)
    if homepage_norm is None:
        return
    for company in companies:
        company_id = get_str(company, "company_id")
        website = get_str(company, "website_url")
        if company_id is None or website is None:
            continue
        if norm.url_norm(website) == homepage_norm:
            out[(project_id, company_id)] = f"homepage {homepage_norm} == company website"


def _top_contributors(contributions: Sequence[Row]) -> dict[str, list[str]]:
    """PSR ids of top contributors (share >= TOP_CONTRIBUTOR_SHARE) per project."""
    result: dict[str, list[str]] = {}
    for row in contributions:
        project_id = get_str(row, "project_id")
        psr = get_str(row, "source_record_id")
        share = row.get("contribution_share")
        if project_id is None or psr is None or not isinstance(share, int | float):
            continue
        if float(share) >= TOP_CONTRIBUTOR_SHARE:
            result.setdefault(project_id, []).append(psr)
    return result


def _members(rows: Sequence[Row], key: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for row in rows:
        artifact = get_str(row, key)
        psr = get_str(row, "source_record_id")
        if artifact is not None and psr is not None:
            result.setdefault(artifact, []).append(psr)
    return result


def candidate_pairs(
    crosslinks: CrossLinks,
    contributions: Sequence[Row],
    authorships: Sequence[Row],
    officers: Sequence[Row],
) -> dict[tuple[str, str], str]:
    """Candidate person pairs generated by the artifact cross-links.

    Args:
        crosslinks: Stage-1 artifact links.
        contributions: silver.contribution rows.
        authorships: silver.authorship rows.
        officers: silver.officer rows.

    Returns:
        Sorted PSR-id pairs mapped to their cross-link description.
    """
    top = _top_contributors(contributions)
    authors = _members(authorships, "publication_id")
    company_officers = _members(officers, "company_id")
    pairs: dict[tuple[str, str], str] = {}
    for (project_id, pub_id), description in crosslinks.project_publications.items():
        _cross(pairs, top.get(project_id, []), authors.get(pub_id, []), description)
    for (project_id, company_id), description in crosslinks.project_companies.items():
        _cross(pairs, top.get(project_id, []), company_officers.get(company_id, []), description)
    return pairs


def _cross(
    pairs: dict[tuple[str, str], str], left: Sequence[str], right: Sequence[str], description: str
) -> None:
    """Add every distinct cross pair of two member lists to `pairs`."""
    for a in left:
        for b in right:
            if a != b:
                pairs.setdefault(_ordered(a, b), description)


def _ordered(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _shared_email(a: PsrView, b: PsrView) -> str | None:
    shared = sorted(set(a.email_norms) & set(b.email_norms))
    return shared[0] if shared else None


def _login_matches_name(a: PsrView, b: PsrView) -> bool:
    for login_side, name_side in ((a, b), (b, a)):
        login = login_side.github_login
        name = name_side.name_norm
        if login is not None and name is not None and login.lower() == name.replace(" ", ""):
            return True
    return False


def _github_url_on_record(a: PsrView, b: PsrView) -> bool:
    for login_side, url_side in ((a, b), (b, a)):
        login = login_side.github_login
        website = url_side.website_url_norm
        if login is not None and website == f"github.com/{login.lower()}":
            return True
    return False


def _name_jw(a: PsrView, b: PsrView) -> float:
    if a.name_norm is None or b.name_norm is None:
        return 0.0
    return JaroWinkler.similarity(a.name_norm, b.name_norm)


def linkedin_norm(url: str | None) -> str | None:
    """Canonicalize a LinkedIn URL for D7 equality.

    Args:
        url: The URL as observed at the source.

    Returns:
        Scheme-less, www-less, lowercased URL without trailing slash or
        query; None for empty input.
    """
    if url is None:
        return None
    normalized = norm.url_norm(url)
    return normalized.lower() if normalized is not None else None


def _d7_match(a: PsrView, b: PsrView) -> RuleMatch | None:
    """D7: LinkedIn-URL equality between one pair (normalized both sides)."""
    linkedin = linkedin_norm(a.linkedin_url)
    if linkedin is None or linkedin != linkedin_norm(b.linkedin_url):
        return None
    left, right = _ordered(a.source_record_id, b.source_record_id)
    return RuleMatch(
        left,
        right,
        "D7",
        "det_linkedin",
        _CONF_LINKEDIN,
        auto=True,
        evidence={"rule": "D7", "linkedin": linkedin},
    )


def _identifier_matches(a: PsrView, b: PsrView) -> list[RuleMatch]:
    """D1-D4 plus D7: independent-identifier equality between one pair."""
    matches: list[RuleMatch] = []
    left, right = _ordered(a.source_record_id, b.source_record_id)
    if a.orcid is not None and a.orcid == b.orcid:
        matches.append(
            RuleMatch(
                left,
                right,
                "D1",
                "det_orcid",
                _CONF_ORCID,
                auto=True,
                evidence={"rule": "D1", "orcid": a.orcid},
            )
        )
    email = _shared_email(a, b)
    if email is not None:
        matches.append(
            RuleMatch(
                left,
                right,
                "D2",
                "det_email",
                _CONF_EMAIL,
                auto=True,
                evidence={"rule": "D2", "email": email},
            )
        )
    if a.website_url_norm is not None and a.website_url_norm == b.website_url_norm:
        matches.append(
            RuleMatch(
                left,
                right,
                "D3",
                "det_website",
                _CONF_WEBSITE,
                auto=True,
                evidence={"rule": "D3", "website": a.website_url_norm},
            )
        )
    handle = a.twitter_handle is not None and a.twitter_handle == b.twitter_handle
    if handle or _github_url_on_record(a, b):
        evidence: dict[str, Json] = {"rule": "D4"}
        evidence["handle"] = a.twitter_handle if handle else "github url on record"
        matches.append(
            RuleMatch(left, right, "D4", "det_handle", _CONF_HANDLE, auto=True, evidence=evidence)
        )
    linkedin = _d7_match(a, b)
    if linkedin is not None:
        matches.append(linkedin)
    return matches


def deterministic_matches(
    views: Iterable[PsrView], candidates: Mapping[tuple[str, str], str]
) -> list[RuleMatch]:
    """Run D1-D6 over every PSR pair (D5 only over cross-link candidates).

    Args:
        views: The PSR matching views.
        candidates: Stage-1 candidate pairs with descriptions.

    Returns:
        All matches; D6 carries auto=False and routes to review, never a link.
    """
    ordered = sorted(views, key=lambda view: view.source_record_id)
    by_id = {view.source_record_id: view for view in ordered}
    matches: list[RuleMatch] = []
    for index, a in enumerate(ordered):
        for b in ordered[index + 1 :]:
            matches.extend(_identifier_matches(a, b))
            matches.extend(_name_rules(a, b))
    for (left, right), description in sorted(candidates.items()):
        a = by_id.get(left)
        b = by_id.get(right)
        if a is None or b is None:
            continue
        jw = _name_jw(a, b)
        if jw >= NAME_JW_THRESHOLD or _login_matches_name(a, b):
            evidence: dict[str, Json] = {
                "rule": "D5",
                "crosslink": description,
                "name_jw": round(jw, 2),
            }
            matches.append(
                RuleMatch(
                    left,
                    right,
                    "D5",
                    "det_crosslink",
                    _CONF_CROSSLINK,
                    auto=True,
                    evidence=evidence,
                )
            )
    return matches


def _repo_project_by_url(projects: Sequence[Row]) -> dict[str, str]:
    """Normalized repo URL to silver.project id."""
    by_url: dict[str, str] = {}
    for project in projects:
        project_id = get_str(project, "project_id")
        full_name = get_str(project, "full_name")
        if project_id is None or full_name is None:
            continue
        for url in _github_repo_urls(full_name):
            by_url.setdefault(url, project_id)
    return by_url


def hacknation_repo_candidates(
    hacknation_projects: Sequence[Row],
    projects: Sequence[Row],
    contributions: Sequence[Row],
) -> dict[tuple[str, str], str]:
    """D8 candidates: HN project members x core contributors of its githubUrl repo.

    Args:
        hacknation_projects: bronze.hacknation_projects_raw rows.
        projects: silver.project rows.
        contributions: silver.contribution rows.

    Returns:
        Sorted PSR-id pairs mapped to the shared normalized repo URL.
    """
    top = _top_contributors(contributions)
    by_url = _repo_project_by_url(projects)
    pairs: dict[tuple[str, str], str] = {}
    for row in hacknation_projects:
        payload = get_map(row, "payload")
        github_url = get_str(payload, "githubUrl")
        repo_url = norm.url_norm(github_url) if github_url is not None else None
        project_id = by_url.get(repo_url) if repo_url is not None else None
        if repo_url is None or project_id is None:
            continue
        member_psrs = [
            ids.psr_id(HACKNATION_SOURCE, user_id)
            for entry in hacknation_member_entries(payload)
            if (user_id := hacknation_user_id(entry)) is not None
        ]
        _cross_url_pairs(pairs, member_psrs, top.get(project_id, []), repo_url)
    return pairs


def _cross_url_pairs(
    pairs: dict[tuple[str, str], str], left: Sequence[str], right: Sequence[str], url: str
) -> None:
    """Add every distinct cross pair with the shared repo URL as evidence."""
    for a in left:
        for b in right:
            if a != b:
                pairs.setdefault(_ordered(a, b), url)


def hacknation_matches(
    views: Mapping[str, PsrView], candidates: Mapping[tuple[str, str], str]
) -> list[RuleMatch]:
    """D8: gate the Hack Nation repo candidates on a strong name match.

    Args:
        views: PSR views keyed by source_record_id.
        candidates: D8 candidate pairs mapped to their shared repo URL.

    Returns:
        Auto matches at confidence 0.90 (method det_hn_repo).
    """
    matches: list[RuleMatch] = []
    for (left, right), url in sorted(candidates.items()):
        a = views.get(left)
        b = views.get(right)
        if a is None or b is None:
            continue
        jw = _name_jw(a, b)
        if jw < NAME_JW_D8:
            continue
        evidence: dict[str, Json] = {"rule": "D8", "github_url": url, "name_jw": round(jw, 2)}
        matches.append(
            RuleMatch(
                left,
                right,
                "D8",
                "det_hn_repo",
                _CONF_GITHUB_CONTRIB,
                auto=True,
                evidence=evidence,
            )
        )
    return matches


def _name_rules(a: PsrView, b: PsrView) -> list[RuleMatch]:
    """D6: exact name + org agreement; below the auto floor by design."""
    if a.name_norm is None or a.org_norm is None:
        return []
    if a.name_norm != b.name_norm or a.org_norm != b.org_norm:
        return []
    left, right = _ordered(a.source_record_id, b.source_record_id)
    evidence: dict[str, Json] = {"rule": "D6", "name_norm": a.name_norm, "org_norm": a.org_norm}
    return [
        RuleMatch(left, right, "D6", "det_name_org", _CONF_NAME_ORG, auto=False, evidence=evidence)
    ]
