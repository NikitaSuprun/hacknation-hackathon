"""T-QA: pairwise ER precision against the golden set, plus corroboration.

Precision is pairwise: every unordered PSR pair co-linked to one person is a
produced pair; the golden fixture links define truth. Facts corroborate when
at least two independent source types attest the same person-artifact
relationship (directly or via a cross-linked artifact); enrichment never
counts, so single-source and enrichment facts stay provisional.
"""

import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Final

from contracts.models import Json, SinkRow
from scrapers.common.jsonutil import as_sink, get_str

PROVISIONAL_THRESHOLD: Final[int] = 2
_DEPENDENT_SOURCES: Final[frozenset[str]] = frozenset({"enrichment"})


def linked_pairs(link_rows: Iterable[Mapping[str, Json]]) -> frozenset[frozenset[str]]:
    """Unordered PSR pairs co-linked to one person by active links.

    Args:
        link_rows: silver.person_source_link rows.

    Returns:
        The pair set.
    """
    by_person: dict[str, list[str]] = {}
    for row in link_rows:
        person = row.get("person_id")
        psr = row.get("source_record_id")
        if row.get("status") == "active" and isinstance(person, str) and isinstance(psr, str):
            by_person.setdefault(person, []).append(psr)
    pairs: set[frozenset[str]] = set()
    for members in by_person.values():
        ordered = sorted(members)
        for index, a in enumerate(ordered):
            pairs.update(frozenset((a, b)) for b in ordered[index + 1 :])
    return frozenset(pairs)


def precision_report(
    produced_links: Sequence[Mapping[str, Json]],
    golden_links: Sequence[Mapping[str, Json]],
    *,
    cycle_id: str,
    clock: Callable[[], datetime],
) -> SinkRow:
    """Pairwise precision and false-merge rate versus the golden set.

    Args:
        produced_links: Links produced by this run (plus carried state).
        golden_links: The golden-truth link rows.
        cycle_id: The reporting cycle identifier.
        clock: Injected time source.

    Returns:
        One ops.data_quality_report row.
    """
    produced = linked_pairs(produced_links)
    golden = linked_pairs(golden_links)
    correct = len(produced & golden)
    precision = correct / len(produced) if produced else 1.0
    false_merge = (len(produced) - correct) / len(produced) if produced else 0.0
    confidences = sorted(
        float(value)
        for row in produced_links
        if row.get("status") == "active"
        and isinstance(value := row.get("match_confidence"), int | float)
    )
    return {
        "cycle_id": cycle_id,
        "source": "er",
        "reject_rate": None,
        "er_precision": round(precision, 4),
        "false_merge_rate": round(false_merge, 4),
        "coverage": None,
        "confidence_p50": round(statistics.median(confidences), 4) if confidences else None,
        "freshness_days": None,
        "computed_at": clock(),
    }


def corroborate(
    fact_rows: Sequence[dict[str, Json]],
    *,
    artifact_col: str,
    psr_sources: Mapping[str, str],
    attesting_sources: Mapping[str, frozenset[str]],
) -> list[SinkRow]:
    """Recompute corroboration_count / is_provisional; changed rows only.

    A fact's corroboration count is the number of distinct independent source
    types attesting its artifact's person relationship: the fact's own source
    plus the sources supplied for the artifact via cross-links.

    Args:
        fact_rows: contribution/authorship/officer rows.
        artifact_col: The fact's artifact column name.
        psr_sources: source_record_id to source type.
        attesting_sources: Extra attesting source types per artifact id
            (from facts of the same person on cross-linked artifacts).

    Returns:
        Full rows whose corroboration fields changed.
    """
    changed: list[SinkRow] = []
    for row in fact_rows:
        artifact = get_str(row, artifact_col)
        psr = get_str(row, "source_record_id")
        if artifact is None or psr is None:
            continue
        own = psr_sources.get(psr)
        sources = set(attesting_sources.get(artifact, frozenset()))
        if own is not None:
            sources.add(own)
        count = len(sources - _DEPENDENT_SOURCES)
        provisional = count < PROVISIONAL_THRESHOLD
        if row.get("corroboration_count") == count and row.get("is_provisional") == provisional:
            continue
        updated: SinkRow = {key: as_sink(value) for key, value in row.items()}
        updated["corroboration_count"] = count
        updated["is_provisional"] = provisional
        changed.append(updated)
    return changed
