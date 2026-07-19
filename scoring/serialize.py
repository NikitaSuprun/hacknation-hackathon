# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Fixture-identical JSONL rendering.

The golden tests byte-compare job output against fixtures/data/gold.*.jsonl,
so this rendering must stay a mirror of fixtures/build.write_jsonl: sorted
keys, ensure_ascii=False, temporals via isoformat, one trailing newline.
"""

import json
from collections.abc import Sequence
from datetime import date, datetime

from contracts.models import SinkRow


def _temporal_default(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(str(type(value)))


def to_jsonl_lines(rows: Sequence[SinkRow]) -> str:
    """Render rows exactly as fixtures/build.write_jsonl writes them.

    Args:
        rows: Rows in DDL column shape.

    Returns:
        One JSON object per line plus a trailing newline.
    """
    lines = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, default=_temporal_default)
        for row in rows
    ]
    return "\n".join(lines) + "\n"
