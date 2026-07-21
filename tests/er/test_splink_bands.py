"""T8: pinned-parameter Splink bands are correct and run-to-run deterministic."""

from er.models import psr_view
from er.pipeline import ErInputs
from er.splink_job import band_of, features_from_vector, filter_unlinked_pairs, score_pairs
from fixtures import build as fx


def _ordered(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def test_fixture_pairs_land_in_their_bands(inputs: ErInputs) -> None:
    views = [psr_view(row) for row in inputs.psr_rows]
    pairs = {(pair.left, pair.right): pair for pair in score_pairs(views, train=False)}
    wei_a = pairs[_ordered(fx.PSR_WEI_A_GITHUB, fx.PSR_WEI_A_OPENALEX)]
    jonas = pairs[_ordered(fx.PSR_JONAS_GITHUB, fx.PSR_JONAS_ZEFIX)]
    wei_cross_oa = pairs[_ordered(fx.PSR_WEI_B_OPENALEX, fx.PSR_WEI_A_OPENALEX)]
    wei_cross_gh = pairs[_ordered(fx.PSR_WEI_B_OPENALEX, fx.PSR_WEI_A_GITHUB)]
    assert band_of(wei_a.probability) == "adjudicate"
    assert band_of(jonas.probability) == "adjudicate"
    assert band_of(wei_cross_oa.probability) == "review"
    assert band_of(wei_cross_gh.probability) == "review"
    # Unrelated persons never surface: everything scored shares a block AND a
    # name; no cross-persona pair (Fischer x Zhang, Berger x Keller, ...) is in.
    surfaced = set(pairs)
    for left, right in surfaced:
        sources = {left, right}
        assert not (fx.PSR_LENA_GITHUB in sources and fx.PSR_WEI_A_GITHUB in sources)
        assert not (fx.PSR_NILS_GITHUB in sources and fx.PSR_JONAS_GITHUB in sources)


def test_scores_are_deterministic_across_runs(inputs: ErInputs) -> None:
    views = [psr_view(row) for row in inputs.psr_rows]
    first = score_pairs(views, train=False)
    second = score_pairs(views, train=False)
    assert first == second


def test_comparison_vector_lands_in_evidence(inputs: ErInputs) -> None:
    views = [psr_view(row) for row in inputs.psr_rows]
    pairs = {(pair.left, pair.right): pair for pair in score_pairs(views, train=False)}
    wei_cross = pairs[_ordered(fx.PSR_WEI_B_OPENALEX, fx.PSR_WEI_A_OPENALEX)]
    vector = wei_cross.comparison["comparison_vector"]
    assert isinstance(vector, dict)
    assert set(vector) == {
        "name_norm",
        "primary_email_norm",
        "org_norm",
        "country_code",
        "keywords",
    }
    features = features_from_vector(dict(wei_cross.comparison))
    assert features["name_norm"] == "exact"
    assert features["org_norm"] == "mismatch"
    assert features["country_code"] == "mismatch"


def test_filter_drops_pairs_with_both_sides_linked(inputs: ErInputs) -> None:
    views = [psr_view(row) for row in inputs.psr_rows]
    pairs = score_pairs(views, train=False)
    linked = frozenset(str(row["source_record_id"]) for row in inputs.link_rows)
    assert filter_unlinked_pairs(pairs, linked) == []
