"""Live-mode SQL text for the /v1 proxy.

Every identifier comes from the frozen READABLE_NAMES allowlist plus a
require_identifier-guarded catalog, and rows travel back as to_json(struct(*))
strings so VARIANT and complex columns decode uniformly — the reason the
per-file S608 ignore in ruff.toml is safe.
"""

from typing import Final

from scrapers.common.state import require_identifier

READABLE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "gold.thesis",
        "gold.score_weights",
        "gold.ideal_candidate",
        "gold.candidate_pool",
        "gold.venture",
        "gold.venture_member",
        "gold.venture_score",
        "gold.venture_gaps",
        "gold.memo",
        "gold.outreach",
        "gold.interview",
        "gold.score_run",
        "gold.person_features",
        "gold.institution_score",
        "gold.v_ranked_ventures",
        "gold.v_venture_team",
        "gold.v_person_network",
        "gold.v_person_similarity",
        "gold.v_person_signals",
        "silver.person",
        "silver.person_connection",
        "silver.person_source_link",
        "silver.person_source_record",
        "silver.project",
        "silver.company",
        "silver.publication",
        "silver.contribution",
        "silver.authorship",
        "silver.officer",
        "bronze.zefix_sogc_raw",
        "ops.erasure_suppression",
    }
)


class UnknownReadTargetError(KeyError):
    """A read was attempted against a name outside the frozen allowlist."""

    def __init__(self, name: str) -> None:
        """Name the rejected target."""
        super().__init__(f"{name} is not a readable table or view for the app")


def select_rows_sql(catalog: str, name: str) -> str:
    """One-column SELECT returning every row as a JSON string.

    Args:
        catalog: The target catalog (identifier-guarded).
        name: Schema-qualified table or view from READABLE_NAMES.

    Returns:
        The SQL text.

    Raises:
        UnknownReadTargetError: If the name is not allowlisted.
    """
    if name not in READABLE_NAMES:
        raise UnknownReadTargetError(name)
    return f"SELECT to_json(struct(*)) FROM {require_identifier(catalog)}.{name}"
