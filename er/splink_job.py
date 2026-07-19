# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Stage 3: the Splink probabilistic pass (DuckDB backend, run locally).

Untyped vendor surface (splink + duckdb) is confined to this module. Offline
mode pins every m/u probability and the prior instead of EM training, so
predict() is fully deterministic run-to-run; `train=True` switches to random-
sampling u estimation plus EM sessions for live data. The fixed parameters are
tuned so the fixture personas land in their intended bands: the two Wei-Zhang-A
identities and the two Jonas Kellers in the adjudication band, Wei Zhang B
against Wei Zhang A in the review band.
"""

from collections.abc import Iterable, Sequence
from typing import Final

from contracts.models import Json
from er.models import PsrView, ScoredPair

BAND_AUTO: Final[float] = 0.90
BAND_ADJUDICATE: Final[float] = 0.60
BAND_REVIEW: Final[float] = 0.45

# Fellegi-Sunter parameters, fixed for determinism (no EM in offline mode).
_PRIOR: Final[float] = 0.0005
_NAME_M: Final[tuple[float, ...]] = (0.85, 0.06, 0.04, 0.03, 0.02)
_NAME_U: Final[tuple[float, ...]] = (0.00015, 0.0005, 0.001, 0.01, 0.98835)
_EMAIL_M: Final[tuple[float, ...]] = (0.90, 0.04, 0.03, 0.02, 0.01)
_EMAIL_U: Final[tuple[float, ...]] = (0.0001, 0.001, 0.005, 0.01, 0.9839)
_ORG_M: Final[tuple[float, ...]] = (0.70, 0.24)
_ORG_U: Final[tuple[float, ...]] = (0.60, 0.40)
_COUNTRY_M: Final[tuple[float, ...]] = (0.13, 0.675)
_COUNTRY_U: Final[tuple[float, ...]] = (0.10, 0.90)
_KEYWORDS_M: Final[tuple[float, ...]] = (0.04, 0.13, 0.682)
_KEYWORDS_U: Final[tuple[float, ...]] = (0.01, 0.10, 0.89)

_COMPARISON_COLUMNS: Final[tuple[str, ...]] = (
    "name_norm",
    "primary_email_norm",
    "org_norm",
    "country_code",
    "keywords",
)
# Highest comparison-vector value (the exact-match level) per column.
_TOP_LEVEL: Final[dict[str, int]] = {
    "name_norm": 4,
    "primary_email_norm": 4,
    "org_norm": 1,
    "country_code": 1,
    "keywords": 2,
}
_TRAIN_SAMPLE_PAIRS: Final[float] = 1e6


def _record(view: PsrView) -> dict[str, object]:
    """Render one PSR view as a Splink input record (empty arrays become NULL)."""
    return {
        "unique_id": view.source_record_id,
        "name_norm": view.name_norm,
        "first_name": view.first_name,
        "last_name": view.last_name,
        "primary_email_norm": view.email_norms[0] if view.email_norms else None,
        "email_domain": view.email_domain,
        "org_norm": view.org_norm,
        "country_code": view.country_code,
        "github_login": view.github_login,
        "keywords": list(view.keywords) if view.keywords else None,
    }


def score_pairs(views: Sequence[PsrView], *, train: bool) -> list[ScoredPair]:
    """Score candidate pairs with Splink and keep those above the drop band.

    Args:
        views: Every PSR in scope (all of them - term frequencies must be
            stable regardless of link state; filter pairs downstream).
        train: When True, estimate u by random sampling plus EM sessions
            (live mode); when False, use the pinned deterministic parameters.

    Returns:
        Scored pairs at probability >= BAND_REVIEW, sorted by pair id.
    """
    if len(views) < 2:  # noqa: PLR2004 - a single record has no pairs
        return []
    predictions = _predict([_record(view) for view in views], train=train)
    pairs: list[ScoredPair] = []
    for row in predictions:
        left = str(row["unique_id_l"])
        right = str(row["unique_id_r"])
        if left > right:
            left, right = right, left
        probability = float(str(row["match_probability"]))
        vector: dict[str, Json] = {
            column: int(str(row[f"gamma_{column}"])) for column in _COMPARISON_COLUMNS
        }
        comparison: dict[str, Json] = {
            "comparison_vector": vector,
            "probability": round(probability, 6),
        }
        pairs.append(
            ScoredPair(left=left, right=right, probability=probability, comparison=comparison)
        )
    return sorted(pairs, key=lambda pair: (pair.left, pair.right))


def _predict(records: list[dict[str, object]], *, train: bool) -> list[dict[str, object]]:
    """Run the Splink linker; every untyped vendor call lives here."""
    import pandas  # pyright: ignore[reportMissingTypeStubs] - vendor ships no stubs # noqa: PLC0415 - lazy vendor import
    import splink.comparison_library as cl  # noqa: PLC0415 - lazy vendor import by design
    from splink import (  # noqa: PLC0415 - lazy vendor import by design
        ColumnExpression,
        DuckDBAPI,
        Linker,
        SettingsCreator,
        block_on,
    )
    from splink.blocking_rule_library import CustomRule  # noqa: PLC0415 - lazy vendor import

    # Offline, NameComparison sees a transformed (non-pure) expression: its
    # hardwired exact-level term-frequency adjustment would otherwise swamp
    # the pinned weights on a small frame. lower() is a no-op on name_norm.
    name_column = "name_norm" if train else ColumnExpression("name_norm").lower()
    name = cl.NameComparison(name_column)
    email = cl.EmailComparison("primary_email_norm")
    org = cl.ExactMatch("org_norm").configure(term_frequency_adjustments=True)
    country = cl.ExactMatch("country_code")
    keywords = cl.ArrayIntersectAtSizes("keywords", [3, 1])
    if not train:
        name = name.configure(m_probabilities=list(_NAME_M), u_probabilities=list(_NAME_U))
        email = email.configure(m_probabilities=list(_EMAIL_M), u_probabilities=list(_EMAIL_U))
        org = org.configure(m_probabilities=list(_ORG_M), u_probabilities=list(_ORG_U))
        country = country.configure(
            m_probabilities=list(_COUNTRY_M), u_probabilities=list(_COUNTRY_U)
        )
        keywords = keywords.configure(
            m_probabilities=list(_KEYWORDS_M), u_probabilities=list(_KEYWORDS_U)
        )
    settings = SettingsCreator(
        link_type="dedupe_only",
        probability_two_random_records_match=_PRIOR,
        blocking_rules_to_generate_predictions=[
            block_on("last_name"),
            block_on("email_domain"),
            block_on("substr(first_name,1,1)", "org_norm"),
            CustomRule("l.github_login = replace(r.name_norm, ' ', '')"),
        ],
        comparisons=[name, email, org, country, keywords],
        retain_intermediate_calculation_columns=True,
    )
    frame = pandas.DataFrame(records)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType] - vendor API is untyped
    linker = Linker(  # pyright: ignore[reportUnknownVariableType] - vendor API is untyped
        frame,  # pyright: ignore[reportUnknownArgumentType, reportArgumentType] - vendor API is untyped # ty: ignore[invalid-argument-type] - splink accepts DataFrames
        settings,
        db_api=DuckDBAPI(),
    )
    if train:
        linker.training.estimate_u_using_random_sampling(max_pairs=_TRAIN_SAMPLE_PAIRS)  # pyright: ignore[reportUnknownMemberType] - vendor API is untyped
        for rule in ("last_name", "email_domain"):
            linker.training.estimate_parameters_using_expectation_maximisation(  # pyright: ignore[reportUnknownMemberType] - vendor API is untyped
                block_on(rule)
            )
    predictions = linker.inference.predict(threshold_match_probability=BAND_REVIEW)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType] - vendor API is untyped
    return predictions.as_record_dict()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType] - vendor API is untyped


def band_of(probability: float) -> str:
    """Name the action band of one score.

    Args:
        probability: The Splink match probability.

    Returns:
        'auto', 'adjudicate', 'review', or 'drop'.
    """
    if probability >= BAND_AUTO:
        return "auto"
    if probability >= BAND_ADJUDICATE:
        return "adjudicate"
    if probability >= BAND_REVIEW:
        return "review"
    return "drop"


def features_from_vector(comparison: dict[str, Json]) -> dict[str, Json]:
    """Human-readable feature map for review rows from a comparison vector.

    Args:
        comparison: The stored comparison evidence.

    Returns:
        Per-column 'exact' / 'partial' / 'mismatch' / 'null' labels.
    """
    vector = comparison.get("comparison_vector")
    if not isinstance(vector, dict):
        return {}
    features: dict[str, Json] = {}
    for column, value in vector.items():
        if not isinstance(value, int):
            continue
        features[column] = _label(column, value)
    return features


def _label(column: str, value: int) -> str:
    if value < 0:
        return "null"
    if value == _TOP_LEVEL.get(column, 1):
        return "exact"
    return "mismatch" if value == 0 else "partial"


def filter_unlinked_pairs(pairs: Iterable[ScoredPair], linked: frozenset[str]) -> list[ScoredPair]:
    """Drop pairs whose two members are both already actively linked.

    Args:
        pairs: Scored pairs.
        linked: source_record_ids holding an active link.

    Returns:
        The pairs still in play.
    """
    return [pair for pair in pairs if pair.left not in linked or pair.right not in linked]
