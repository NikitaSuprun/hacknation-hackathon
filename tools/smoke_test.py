# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Day-0 model smoke test against the Free Edition warehouse (`poe smoke`).

Proves connectivity (SELECT 1), the embedding endpoint (1024 floats), and
records which databricks-claude-* endpoints resolve, so the Anthropic-API
fallback decision is grounded in observed availability, not the docs.
"""

import contextlib
import sys
from typing import Final

from tools.settings import load_databricks_settings
from tools.warehouse import Warehouse, WarehouseError

EMBEDDING_MODEL: Final[str] = "databricks-gte-large-en"
EMBEDDING_DIM: Final[int] = 1024

CLAUDE_ENDPOINTS: Final[tuple[str, ...]] = (
    "databricks-claude-opus-4-8",
    "databricks-claude-opus-4-7",
    "databricks-claude-opus-4-6",
    "databricks-claude-sonnet-5",
    "databricks-claude-sonnet-4-6",
    "databricks-claude-haiku-4-5",
    "databricks-claude-fable-5",
)


def _select_one(warehouse: Warehouse) -> bool:
    rows = warehouse.execute("SELECT 1")
    return int(str(rows[0][0])) == 1


def _embedding_dim(warehouse: Warehouse) -> int:
    rows = warehouse.execute(f"SELECT size(ai_query('{EMBEDDING_MODEL}', 'hi'))")
    return int(str(rows[0][0]))


def _claude_resolves(warehouse: Warehouse, endpoint: str) -> bool:
    with contextlib.suppress(WarehouseError):
        warehouse.execute(f"SELECT ai_query('{endpoint}', 'Reply with the word OK')")
        return True
    return False


def main() -> int:
    """Run the smoke checks and print the availability report.

    Returns:
        Process exit code (1 when connectivity or embeddings fail; missing
        Claude endpoints are reported, not fatal - that is what the
        Anthropic fallback is for).
    """
    warehouse = Warehouse(load_databricks_settings())
    if not _select_one(warehouse):
        sys.stderr.write("FAIL  SELECT 1\n")
        return 1
    sys.stdout.write("PASS  SELECT 1 via databricks-sql-connector\n")

    dim = _embedding_dim(warehouse)
    if dim != EMBEDDING_DIM:
        sys.stderr.write(f"FAIL  {EMBEDDING_MODEL} returned {dim} floats (need {EMBEDDING_DIM})\n")
        return 1
    sys.stdout.write(f"PASS  {EMBEDDING_MODEL} returns {EMBEDDING_DIM} floats\n")

    unavailable = 0
    for endpoint in CLAUDE_ENDPOINTS:
        if _claude_resolves(warehouse, endpoint):
            sys.stdout.write(f"PASS  {endpoint} resolves\n")
        else:
            unavailable += 1
            sys.stdout.write(f"MISS  {endpoint} unavailable on this workspace\n")
    if unavailable:
        sys.stdout.write(
            "Record the fallback decision in docs/contract.md: unavailable endpoints "
            "route to the Anthropic API (Message Batches for adjudication).\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
