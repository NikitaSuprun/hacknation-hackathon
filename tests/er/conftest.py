# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Shared ER test plumbing: fixture IO, byte rendering, cached pipeline runs."""

import json
import logging
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Final

import pytest

from contracts.models import Json, SinkRow
from er.offline import FIXTURE_DATA_DIR, offline_deps, offline_inputs
from er.pipeline import ALL_STAGES, ErInputs, ErOutputs, run_pipeline

logging.getLogger("splink").setLevel(logging.CRITICAL)

DATA_DIR: Final[Path] = FIXTURE_DATA_DIR


def _temporal(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(str(type(value)))


def render(row: SinkRow) -> str:
    """Render one row exactly as fixtures/build.write_jsonl does."""
    return json.dumps(row, ensure_ascii=False, sort_keys=True, default=_temporal)


def as_json_rows(rows: list[SinkRow]) -> list[dict[str, Json]]:
    """Round-trip produced rows through the fixture serialization."""
    parsed: list[dict[str, Json]] = [json.loads(render(row)) for row in rows]
    return parsed


def fixture_lines(table: str) -> list[str]:
    """The committed JSONL lines of one fixture table."""
    path = DATA_DIR / f"{table}.jsonl"
    return path.read_text(encoding="utf-8").splitlines()


def fixture_rows(table: str) -> list[dict[str, Json]]:
    """The committed rows of one fixture table."""
    return [json.loads(line) for line in fixture_lines(table)]


@pytest.fixture(scope="session")
def inputs() -> ErInputs:
    return offline_inputs()


@pytest.fixture(scope="session")
def scratch_outputs(inputs: ErInputs) -> ErOutputs:
    """One from-scratch run: fixture PSR universe, no links, no verdicts."""
    scratch = replace(inputs, link_rows=[], adjudication_rows=[])
    return run_pipeline(scratch, offline_deps(inputs), stages=ALL_STAGES)


@pytest.fixture(scope="session")
def steady_outputs(inputs: ErInputs) -> ErOutputs:
    """One run over the committed fixture state (everything already linked)."""
    return run_pipeline(inputs, offline_deps(inputs), stages=ALL_STAGES)
