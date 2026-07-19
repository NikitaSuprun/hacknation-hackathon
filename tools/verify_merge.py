# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Staged T3 acceptance against a live warehouse (run via `poe verify-merge`).

Proves on dealflow_dev: a double-run reports 0 inserted / 0 updated, a
changed-hash row updates, and a seeded suppressed key is blocked.
"""

import sys
from datetime import UTC, datetime
from typing import Final

from tools.db import DatabricksSink, content_hash
from tools.settings import load_databricks_settings
from tools.warehouse import Warehouse

_TABLE: Final[str] = "bronze.github_users_raw"
_SUPPRESSED_USER_ID: Final[int] = 999001
_BATCH_SIZE: Final[int] = 2


def _user_row(user_id: int, login: str, bio: str) -> dict[str, object]:
    now = datetime.now(tz=UTC)
    payload: dict[str, object] = {"login": login, "bio": bio}
    return {
        "user_id": user_id,
        "login": login,
        "payload": payload,
        "content_hash": content_hash(payload),
        "source_url": f"https://api.github.com/users/{login}",
        "scraped_at": now,
        "ingested_at": now,
        "scrape_run_id": "verify-merge",
    }


def _seed_suppression(warehouse: Warehouse) -> None:
    statement = (
        "MERGE INTO dealflow_dev.ops.erasure_suppression t "  # noqa: S608 - constant test key, no user input
        f"USING (SELECT 'github' AS source, sha2('{_SUPPRESSED_USER_ID}', 256) AS source_key_hash, "
        "current_timestamp() AS created_at) s "
        "ON t.source = s.source AND t.source_key_hash = s.source_key_hash "
        "WHEN NOT MATCHED THEN INSERT (source, source_key_hash, created_at) "
        "VALUES (s.source, s.source_key_hash, s.created_at)"
    )
    warehouse.execute(statement)


def _check(label: str, ok: bool, failures: list[str]) -> None:  # noqa: FBT001 - verdict flag is the whole point
    sys.stdout.write(f"{'PASS' if ok else 'FAIL'}  {label}\n")
    if not ok:
        failures.append(label)


def main() -> int:
    """Run the three T3 acceptance checks against dealflow_dev.

    Returns:
        Process exit code (1 when any check failed).
    """
    settings = load_databricks_settings()
    sink = DatabricksSink(settings, catalog="dealflow_dev")
    warehouse = Warehouse(settings)
    failures: list[str] = []

    rows = [_user_row(999101, "verify-a", "first"), _user_row(999102, "verify-b", "first")]
    first = sink.upsert(_TABLE, rows, ["user_id"], variant_cols=frozenset({"payload"}))
    second = sink.upsert(_TABLE, rows, ["user_id"], variant_cols=frozenset({"payload"}))
    _check(
        "double-run inserts 0 and updates 0", (second.inserted, second.updated) == (0, 0), failures
    )
    _check(
        "first run inserted or refreshed rows",
        first.inserted + first.skipped_unchanged == _BATCH_SIZE,
        failures,
    )

    changed = [_user_row(999101, "verify-a", "second"), _user_row(999102, "verify-b", "first")]
    third = sink.upsert(_TABLE, changed, ["user_id"], variant_cols=frozenset({"payload"}))
    _check(
        "changed-hash row updates exactly once", (third.inserted, third.updated) == (0, 1), failures
    )

    _seed_suppression(warehouse)
    blocked = sink.upsert(
        _TABLE,
        [_user_row(_SUPPRESSED_USER_ID, "verify-erased", "must not land")],
        ["user_id"],
        variant_cols=frozenset({"payload"}),
    )
    count_rows = warehouse.execute(
        f"SELECT count(*) FROM dealflow_dev.{_TABLE} WHERE user_id = {_SUPPRESSED_USER_ID}"  # noqa: S608 - constant test key, no user input
    )
    absent = int(str(count_rows[0][0])) == 0
    _check("suppressed key is blocked and absent", blocked.suppressed == 1 and absent, failures)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
