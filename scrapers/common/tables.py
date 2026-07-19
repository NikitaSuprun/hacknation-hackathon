# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Merge keys and VARIANT columns for every table the scrapers write.

Deliberately duplicated from fixtures/load.py (which drags in the fixture
builder); both sides are golden-tested against the DDL contract.
"""

from typing import Final

BATCH_SIZE: Final[int] = 500
REJECTS_TABLE: Final[str] = "bronze._rejects"

MERGE_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "bronze.github_repos_raw": ("repo_id",),
    "bronze.github_users_raw": ("user_id",),
    "bronze.github_commits_raw": ("repo_id", "sha"),
    "bronze.arxiv_papers_raw": ("arxiv_id",),
    "bronze.openalex_works_raw": ("openalex_id",),
    "bronze.s2_papers_raw": ("s2_id",),
    "bronze.paper_code_links": ("repo_url", "paper_arxiv_id"),
    "bronze._rejects": ("source", "natural_key"),
    "ops.scrape_state": ("source",),
}

# bronze._rejects.raw is STRING in the DDL, not VARIANT.
VARIANT_COLS: Final[dict[str, frozenset[str]]] = {
    "bronze.github_repos_raw": frozenset({"payload"}),
    "bronze.github_users_raw": frozenset({"payload"}),
    "bronze.github_commits_raw": frozenset({"payload"}),
    "bronze.arxiv_papers_raw": frozenset({"payload"}),
    "bronze.openalex_works_raw": frozenset({"payload"}),
    "bronze.s2_papers_raw": frozenset({"payload"}),
    "ops.scrape_state": frozenset({"cursor"}),
}
