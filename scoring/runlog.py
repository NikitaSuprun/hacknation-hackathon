# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""ops.llm_run_log accounting: one row per (run, stage) with tokens/searches/cost.

The table carries no primary key in the DDL, so the merge keys fall back to
("run_id", "stage") — the shape every WS logs spend under.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from contracts.interfaces import LLMClient, Sink
from contracts.models import Json, LLMResponse, SinkRow, UpsertResult
from tools.ddl_registry import table_schema
from tools.llm import prompt_tag

LLM_RUN_LOG_TABLE: Final[str] = "ops.llm_run_log"
FALLBACK_KEYS: Final[tuple[str, str]] = ("run_id", "stage")


@dataclass(frozen=True, slots=True)
class LlmUsage:
    """Aggregated consumption of one pipeline stage."""

    input_tokens: int
    output_tokens: int
    searches: int
    cost_usd: float


def run_log_keys() -> list[str]:
    """Merge keys for ops.llm_run_log (registry PK, else the fallback pair).

    Returns:
        The key column names.
    """
    schema = table_schema(LLM_RUN_LOG_TABLE)
    return list(schema.primary_key or FALLBACK_KEYS)


def build_run_log_row(
    run_id: str, stage: str, model: str, usage: LlmUsage, at: datetime
) -> SinkRow:
    """Build one llm_run_log row in DDL column shape.

    Args:
        run_id: The pipeline run id.
        stage: The pipeline stage ('stage_b:market', 'memo', ...).
        model: The model or endpoint used.
        usage: Aggregated tokens/searches/cost.
        at: Event timestamp.

    Returns:
        The row.
    """
    return {
        "run_id": run_id,
        "stage": stage,
        "model": model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "searches": usage.searches,
        "cost_usd": usage.cost_usd,
        "at": at,
    }


class RunLog:
    """Accumulates spend rows for one run and flushes them through the sink."""

    def __init__(self, sink: Sink, run_id: str, clock: Callable[[], datetime]) -> None:
        """Bind the sink, the run id, and the injected clock."""
        self._sink: Final[Sink] = sink
        self._run_id: Final[str] = run_id
        self._clock: Final[Callable[[], datetime]] = clock
        self.rows: Final[list[SinkRow]] = []

    def record(self, stage: str, model: str, usage: LlmUsage) -> SinkRow:
        """Append one spend row for a stage.

        Args:
            stage: The pipeline stage.
            model: The model or endpoint used.
            usage: Aggregated tokens/searches/cost.

        Returns:
            The recorded row.
        """
        row = build_run_log_row(self._run_id, stage, model, usage, self._clock())
        self.rows.append(row)
        return row

    def flush(self) -> UpsertResult | None:
        """MERGE the accumulated rows; a run with no LLM calls writes nothing.

        Returns:
            The upsert counts, or None when there was nothing to write.
        """
        if not self.rows:
            return None
        return self._sink.upsert(LLM_RUN_LOG_TABLE, list(self.rows), run_log_keys())


class CountingLLMClient:
    """LLMClient wrapper counting calls so jobs can report spend per stage."""

    def __init__(self, inner: LLMClient) -> None:
        """Wrap the real client; counts start at zero."""
        self._inner: Final[LLMClient] = inner
        self.completions: Final[list[str]] = []
        self.embeddings: int = 0

    def complete(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Json] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Delegate one completion and record its prompt tag.

        Args:
            prompt: The prompt text.
            schema: Optional JSON schema for structured output.
            model: Optional model override.

        Returns:
            The inner client's response.
        """
        self.completions.append(prompt_tag(prompt))
        return self._inner.complete(prompt, schema=schema, model=model)

    def embed(self, text: str) -> list[float]:
        """Delegate one embedding and count it.

        Args:
            text: The text to embed.

        Returns:
            The inner client's embedding.
        """
        self.embeddings += 1
        return self._inner.embed(text)
