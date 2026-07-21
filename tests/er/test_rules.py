"""T7: artifact cross-links and the deterministic rules D1-D6."""

from er.models import psr_view
from er.pipeline import ErInputs
from er.rules import build_crosslinks, candidate_pairs, deterministic_matches
from fixtures import build as fx


def _ordered(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def test_crosslinks_cover_readme_code_urls_and_homepage(inputs: ErInputs) -> None:
    links = build_crosslinks(
        inputs.projects, inputs.publications, inputs.companies, inputs.paper_code_links
    )
    assert (fx.GRASP_PROJECT, fx.GRASP_PUBLICATION) in links.project_publications
    assert (fx.FASTSIM_PROJECT, fx.BERGER_PUBLICATION) in links.project_publications
    assert (fx.GRASP_PROJECT, fx.GRASP_COMPANY) in links.project_companies


def test_candidate_pairs_are_top_contributors_times_authors(inputs: ErInputs) -> None:
    links = build_crosslinks(
        inputs.projects, inputs.publications, inputs.companies, inputs.paper_code_links
    )
    pairs = candidate_pairs(links, inputs.contributions, inputs.authorships, inputs.officers)
    assert _ordered(fx.PSR_LENA_GITHUB, fx.PSR_LENA_OPENALEX) in pairs
    assert _ordered(fx.PSR_LENA_GITHUB, fx.PSR_LENA_ZEFIX) in pairs
    assert _ordered(fx.PSR_NILS_GITHUB, fx.PSR_NILS_ARXIV) in pairs
    # Wei's contribution share (0.38) is below the top-contributor floor.
    assert _ordered(fx.PSR_WEI_A_GITHUB, fx.PSR_WEI_A_OPENALEX) not in pairs


def test_deterministic_rules_fire_with_method_and_evidence(inputs: ErInputs) -> None:
    views = [psr_view(row) for row in inputs.psr_rows]
    links = build_crosslinks(
        inputs.projects, inputs.publications, inputs.companies, inputs.paper_code_links
    )
    pairs = candidate_pairs(links, inputs.contributions, inputs.authorships, inputs.officers)
    matches = {
        (match.left, match.right, match.rule): match
        for match in deterministic_matches(views, pairs)
    }
    email = matches[(*_ordered(fx.PSR_NILS_GITHUB, fx.PSR_NILS_ARXIV), "D2")]
    assert email.method == "det_email"
    assert email.confidence == 0.98
    assert email.auto is True
    assert email.evidence == {"rule": "D2", "email": "nils@berger.dev"}
    orcid = matches[(*_ordered(fx.PSR_AISHA_OPENALEX, fx.PSR_AISHA_ENRICHMENT), "D1")]
    assert orcid.method == "det_orcid"
    assert orcid.evidence == {"rule": "D1", "orcid": "0000-0001-5109-3700"}
    crosslink = matches[(*_ordered(fx.PSR_LENA_GITHUB, fx.PSR_LENA_ZEFIX), "D5")]
    assert crosslink.method == "det_crosslink"
    assert crosslink.confidence == 0.92
    assert crosslink.evidence["name_jw"] == 1.0
    name_org = matches[(*_ordered(fx.PSR_WEI_A_GITHUB, fx.PSR_WEI_A_OPENALEX), "D6")]
    assert name_org.auto is False
    assert name_org.confidence == 0.85


def test_no_name_only_merges(inputs: ErInputs) -> None:
    # The two Wei Zhangs and the two Jonas Kellers share exact names but no
    # identifier, org, or cross-link: no auto rule may fire on any such pair.
    views = [psr_view(row) for row in inputs.psr_rows]
    matches = deterministic_matches(views, {})
    wei_b_pairs = [
        match
        for match in matches
        if fx.PSR_WEI_B_OPENALEX in (match.left, match.right) and match.auto
    ]
    jonas_pairs = [
        match for match in matches if fx.PSR_JONAS_ZEFIX in (match.left, match.right) and match.auto
    ]
    assert wei_b_pairs == []
    assert jonas_pairs == []
