# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Composition root for the scoring jobs (the only place constructors live).

`--fixtures --dry-run` is the zero-credential CI path: NullSink plus the
ScriptedLLMClient over scoring.scripted, frozen fixture clock, deterministic
ids. Live runs read Databricks settings (and ANTHROPIC_API_KEY for Stage B)
and fail fast when configuration is missing.
"""

import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import count
from typing import Final

from structlog.typing import FilteringBoundLogger

from contracts.interfaces import LLMClient, Sink
from fixtures.fake_embedding import fake_embedding
from scoring.scripted import FIXTURE_NOW, fixture_scripts
from scrapers.common.log import get_logger
from scrapers.common.sink import DEFAULT_CATALOG, NullSink
from tools.db import DatabricksSink
from tools.ids import DEALFLOW_NS, new_random_id
from tools.llm import AiQueryLLMClient, AnthropicHttpClient, ScriptedLLMClient
from tools.llm_cli import BACKEND_ENV, CLAUDE_CODE_BACKEND, ClaudeCodeLLMClient
from tools.settings import MissingConfigError, load_databricks_settings
from tools.warehouse import Warehouse

ANTHROPIC_KEY_ENV: Final[str] = "ANTHROPIC_API_KEY"
OFFLINE_ID_PREFIX: Final[str] = "scoring-offline"

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


@dataclass(frozen=True, slots=True)
class ScoringDeps:
    """The injected impurities every scoring job runs against."""

    sink: Sink
    llm: LLMClient
    clock: Clock
    id_factory: IdFactory
    log: FilteringBoundLogger


def sequential_id_factory(prefix: str = OFFLINE_ID_PREFIX) -> IdFactory:
    """Deterministic uuid5 sequence for offline runs.

    Args:
        prefix: Namespace prefix for the sequence.

    Returns:
        A factory yielding uuid5(ns, '<prefix>-<n>') ids.
    """
    counter = count()

    def next_id() -> str:
        return str(uuid.uuid5(DEALFLOW_NS, f"{prefix}-{next(counter)}"))

    return next_id


def _fixture_clock() -> datetime:
    return FIXTURE_NOW


def _live_llm(*, stage_b: bool) -> LLMClient:
    if stage_b:
        # Opt-in route for operators who have a Claude subscription but no API
        # credits; unset, everything behaves exactly as before.
        if os.environ.get(BACKEND_ENV) == CLAUDE_CODE_BACKEND:
            return ClaudeCodeLLMClient()
        api_key = os.environ.get(ANTHROPIC_KEY_ENV)
        if not api_key:
            raise MissingConfigError([ANTHROPIC_KEY_ENV])
        return AnthropicHttpClient(api_key)
    return AiQueryLLMClient(Warehouse(load_databricks_settings()))


def build_scoring_deps(
    *,
    fixtures: bool,
    dry_run: bool,
    catalog: str = DEFAULT_CATALOG,
    stage_b: bool = False,
) -> ScoringDeps:
    """Compose the dependencies for one scoring invocation.

    A live run without the required credentials fails fast with
    MissingConfigError (raised by the settings loaders).

    Args:
        fixtures: Use the scripted fixture layer instead of live models.
        dry_run: Never touch the warehouse (NullSink, no credentials).
        catalog: Target catalog for live runs.
        stage_b: Live runs use the Anthropic HTTP client (web_search capable)
            instead of in-warehouse ai_query.

    Returns:
        The assembled dependencies.
    """
    log = get_logger("scoring")
    offline = fixtures and dry_run
    if offline:
        return ScoringDeps(
            sink=NullSink(),
            llm=ScriptedLLMClient(fixture_scripts(), embedder=fake_embedding),
            clock=_fixture_clock,
            id_factory=sequential_id_factory(),
            log=log,
        )
    sink: Sink = NullSink() if dry_run else DatabricksSink(load_databricks_settings(), catalog)
    llm: LLMClient = (
        ScriptedLLMClient(fixture_scripts(), embedder=fake_embedding)
        if fixtures
        else _live_llm(stage_b=stage_b)
    )
    return ScoringDeps(
        sink=sink,
        llm=llm,
        clock=lambda: datetime.now(UTC),
        id_factory=new_random_id,
        log=log,
    )
