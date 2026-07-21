"""Shared WS-E fixtures: loaded snapshots, offline deps, golden-file access."""

from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest
import structlog

from fixtures import build
from scoring.deps import ScoringDeps, build_scoring_deps
from scoring.snapshot import GoldInputs, SilverSnapshot, load_gold_inputs, load_silver

DATA_DIR: Final[Path] = Path(__file__).resolve().parents[2] / "fixtures" / "data"


def golden_text(table: str) -> str:
    """The committed golden JSONL bytes for one table.

    Args:
        table: Schema-qualified table name.

    Returns:
        The file content.
    """
    return (DATA_DIR / f"{table}.jsonl").read_text(encoding="utf-8")


def golden_lines(table: str) -> list[str]:
    """The committed golden JSONL lines (with newlines) for one table.

    Args:
        table: Schema-qualified table name.

    Returns:
        One string per row, each ending in a newline.
    """
    return golden_text(table).splitlines(keepends=True)


@pytest.fixture(autouse=True)
def _reset_structlog() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction] - pytest autouse fixture
    """Isolate structlog config per test (the CLI runner reconfigures it)."""
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


@pytest.fixture(scope="session")
def silver() -> SilverSnapshot:
    """The fixture silver snapshot."""
    return load_silver(DATA_DIR)


@pytest.fixture(scope="session")
def gold() -> GoldInputs:
    """The fixture gold inputs."""
    return load_gold_inputs(DATA_DIR)


@pytest.fixture
def deps() -> ScoringDeps:
    """Offline scoring deps: NullSink + scripted LLM + frozen clock."""
    return build_scoring_deps(fixtures=True, dry_run=True)


MEMBER_IDS: Final[tuple[str, str]] = (build.LENA, build.WEI_A)
