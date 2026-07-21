"""LLMClient implementations: the ai_query/Anthropic swap point plus a fake.

Three implementations of contracts.interfaces.LLMClient:
- ScriptedLLMClient: deterministic offline stand-in. Responses are keyed by the
  FIRST LINE of the prompt — pipeline prompts start with a stable tag line like
  'TASK:adjudicate pair=<id>' so scripts stay readable and order-independent.
- AiQueryLLMClient: the primary live path — completions and embeddings run
  in-warehouse via ai_query() SQL over any SqlRunner (tools.warehouse fits).
- AnthropicHttpClient: the direct-API fallback (Message Batches, web_search) —
  a thin httpx client so tests drive it through MockTransport; schema-constrained
  completions use a forced tool call. It cannot embed (Anthropic has no
  embeddings endpoint); embed() raises UnsupportedLLMOperationError.
"""

import json
import math
import os
from collections.abc import Callable, Iterable, Mapping
from typing import Final, Protocol, SupportsFloat, cast

import httpx

from contracts.models import Json, LLMResponse
from scrapers.common.jsonutil import as_list, as_mapping

ANTHROPIC_API_URL: Final[str] = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION: Final[str] = "2023-06-01"
DEFAULT_AI_QUERY_MODEL: Final[str] = "databricks-claude-sonnet-4-6"
# Free Edition workspaces ship a subset of Claude endpoints (poe smoke shows
# which); this env var reroutes every ai_query completion to the one that
# exists (e.g. databricks-claude-opus-4-8) without touching per-task tiering.
ENDPOINT_OVERRIDE_ENV: Final[str] = "DATABRICKS_LLM_ENDPOINT"
DEFAULT_ANTHROPIC_MODEL: Final[str] = "claude-opus-4-8"
DEFAULT_MAX_TOKENS: Final[int] = 4_096
EMBEDDING_MODEL: Final[str] = "databricks-gte-large-en"
EMBEDDING_DIM: Final[int] = 1_024
REQUEST_TIMEOUT_SECONDS: Final[float] = 120.0
STRUCTURED_TOOL_NAME: Final[str] = "emit"


class SqlRunner(Protocol):
    """The one-statement query surface ai_query needs (tools.warehouse fits)."""

    def execute(self, statement: str) -> list[tuple[object, ...]]:
        """Run one statement and fetch all rows."""
        ...


class UnsupportedLLMOperationError(RuntimeError):
    """The client cannot perform the requested operation."""

    def __init__(self, client: str, operation: str) -> None:
        """Name the client and operation in the message."""
        super().__init__(f"{client} does not support {operation}")


class UnknownPromptError(KeyError):
    """A scripted client received a prompt with no scripted response."""

    def __init__(self, key: str) -> None:
        """Quote the unmatched prompt tag."""
        super().__init__(f"no scripted response for prompt tag: {key!r}")


class LLMTransportError(RuntimeError):
    """The LLM backend returned an unusable response."""


class EmptyAiQueryResultError(LLMTransportError):
    """An ai_query statement returned no usable row."""

    def __init__(self, endpoint: str) -> None:
        """Name the endpoint in the message."""
        super().__init__(f"ai_query({endpoint}) returned no row")


class EmbeddingShapeError(LLMTransportError):
    """An embedding came back with the wrong dimensionality."""

    def __init__(self, actual: int) -> None:
        """Report actual versus expected dims."""
        super().__init__(f"embedding has {actual} dims, expected {EMBEDDING_DIM}")


class AnthropicStatusError(LLMTransportError):
    """The Anthropic Messages endpoint answered a non-success status."""

    def __init__(self, status: int) -> None:
        """Carry the HTTP status in the message."""
        super().__init__(f"anthropic messages returned HTTP {status}")


def prompt_tag(prompt: str) -> str:
    """The scripting key for a prompt: its first line, stripped.

    Args:
        prompt: The full prompt text.

    Returns:
        The first line.
    """
    return prompt.splitlines()[0].strip() if prompt else ""


class ScriptedLLMClient:
    """Deterministic LLMClient for tests and the credential-free CLI path."""

    def __init__(
        self,
        responses: Mapping[str, LLMResponse],
        *,
        embedder: Callable[[str], list[float]],
        default: LLMResponse | None = None,
    ) -> None:
        """Bind the canned responses (keyed by prompt tag) and the embedder."""
        self._responses: Final[Mapping[str, LLMResponse]] = responses
        self._embedder: Final[Callable[[str], list[float]]] = embedder
        self._default: Final[LLMResponse | None] = default
        self.calls: Final[list[str]] = []

    def complete(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Json] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Return the canned response for the prompt's tag line.

        Args:
            prompt: The prompt; its first line selects the script entry.
            schema: Ignored (scripts are pre-parsed).
            model: Ignored.

        Returns:
            The scripted response.

        Raises:
            UnknownPromptError: If no script entry (and no default) matches.
        """
        del schema, model
        key = prompt_tag(prompt)
        self.calls.append(key)
        response = self._responses.get(key, self._default)
        if response is None:
            raise UnknownPromptError(key)
        return response

    def embed(self, text: str) -> list[float]:
        """Embed via the injected deterministic embedder.

        Args:
            text: The text to embed.

        Returns:
            The embedding vector.
        """
        return self._embedder(text)


def resolve_endpoint(preferred: str) -> str:
    """The ai_query endpoint to use; the workspace override env var wins.

    Args:
        preferred: The task's preferred endpoint.

    Returns:
        The override from DATABRICKS_LLM_ENDPOINT when set, else preferred.
    """
    return os.environ.get(ENDPOINT_OVERRIDE_ENV) or preferred


def response_format(schema: Mapping[str, Json]) -> str:
    """The ai_query responseFormat envelope for a JSON schema.

    Strict mode is on: without it the model treats required properties as
    advisory and intermittently omits them.

    Args:
        schema: A self-contained JSON schema (inline every $ref first).

    Returns:
        The JSON string ai_query expects.
    """
    return json.dumps(
        {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": dict(schema), "strict": True},
        }
    )


def _sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        return vector
    return [component / norm for component in vector]


def _as_floats(raw: object) -> list[float]:
    """Floats from any sequence-like value.

    The SQL connector hands ARRAY<FLOAT> back as a numpy ndarray of numpy
    scalars — neither a list nor Python floats — so accept anything iterable
    whose items convert.

    Args:
        raw: The decoded cell value.

    Returns:
        The floats, or [] when the value is not a numeric sequence.
    """
    if isinstance(raw, str | bytes) or not isinstance(raw, Iterable):
        return []
    floats: list[float] = []
    for item in cast("Iterable[object]", raw):
        if isinstance(item, bool) or not isinstance(item, SupportsFloat):
            return []
        floats.append(float(item))
    return floats


def _parse_vector(value: object) -> list[float]:
    raw: object = value
    if isinstance(raw, str):
        raw = json.loads(raw)
    vector = _as_floats(raw)
    if len(vector) != EMBEDDING_DIM:
        raise EmbeddingShapeError(len(vector))
    return _l2_normalize(vector)


class AiQueryLLMClient:
    """The primary live path: completions and embeddings via in-warehouse ai_query."""

    def __init__(
        self,
        runner: SqlRunner,
        *,
        default_model: str = DEFAULT_AI_QUERY_MODEL,
        embedding_model: str = EMBEDDING_MODEL,
    ) -> None:
        """Bind the SQL runner and model endpoints."""
        self._runner: Final[SqlRunner] = runner
        self._default_model: Final[str] = default_model
        self._embedding_model: Final[str] = embedding_model

    def complete(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Json] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Run one completion through ai_query.

        Args:
            prompt: The prompt text (quoted into the SQL literal).
            schema: When given, the response text is parsed as JSON.
            model: Endpoint override (defaults to the client's model).

        Returns:
            The completion; `parsed` is set when a schema was requested and
            the text parsed as a JSON object.

        Raises:
            EmptyAiQueryResultError: If the statement returned no row.
        """
        endpoint = resolve_endpoint(model or self._default_model)
        arguments = f"{_sql_quote(endpoint)}, {_sql_quote(prompt)}"
        if schema is not None:
            arguments += f", responseFormat => {_sql_quote(response_format(schema))}"
        rows = self._runner.execute(f"SELECT ai_query({arguments})")
        if not rows or rows[0][0] is None:
            raise EmptyAiQueryResultError(endpoint)
        text = str(rows[0][0])
        parsed = _parse_json_object(text) if schema is not None else None
        return LLMResponse(text=text, parsed=parsed, model=endpoint)

    def embed(self, text: str) -> list[float]:
        """Embed via the warehouse embedding endpoint, L2-normalized.

        Args:
            text: The text to embed.

        Returns:
            The unit-norm 1024-dim vector.

        Raises:
            EmptyAiQueryResultError: If the statement returned no row.
        """
        rows = self._runner.execute(
            f"SELECT ai_query({_sql_quote(self._embedding_model)}, {_sql_quote(text)})"
        )
        if not rows or rows[0][0] is None:
            raise EmptyAiQueryResultError(self._embedding_model)
        return _parse_vector(rows[0][0])


def _parse_json_object(text: str) -> Mapping[str, Json] | None:
    try:
        decoded: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    parsed = as_mapping(decoded)
    return parsed or None


class AnthropicHttpClient:
    """The direct-API fallback: Messages endpoint over httpx (web_search capable)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Bind credentials; a transport replays canned responses in tests."""
        self._model: Final[str] = model
        self._client: Final[httpx.Client] = httpx.Client(
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            transport=transport,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    def close(self) -> None:
        """Release the connection pool."""
        self._client.close()

    def messages(self, payload: Mapping[str, Json]) -> dict[str, Json]:
        """POST one raw Messages-API request (the deep-dive agent drives this).

        Args:
            payload: The full request body (model/messages/tools/...).

        Returns:
            The decoded response body.

        Raises:
            AnthropicStatusError: On any non-2xx status.
        """
        response = self._client.post(ANTHROPIC_API_URL, json=payload)
        if response.is_success:
            return as_mapping(response.json())
        raise AnthropicStatusError(response.status_code)

    def complete(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Json] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Run one completion; a schema forces a tool call for structured output.

        Args:
            prompt: The user prompt.
            schema: JSON schema for the response shape, when required.
            model: Model override.

        Returns:
            The completion; with a schema, `parsed` is the forced tool input
            and `text` its canonical JSON rendering.
        """
        chosen = model or self._model
        payload: dict[str, Json] = {
            "model": chosen,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
        if schema is not None:
            payload["tools"] = [
                {
                    "name": STRUCTURED_TOOL_NAME,
                    "description": "Emit the structured answer.",
                    "input_schema": dict(schema),
                }
            ]
            payload["tool_choice"] = {"type": "tool", "name": STRUCTURED_TOOL_NAME}
        body = self.messages(payload)
        parsed = _tool_input(body) if schema is not None else None
        text = _text_content(body) if schema is None else json.dumps(parsed, sort_keys=True)
        return LLMResponse(text=text, parsed=parsed, model=chosen)

    def embed(self, text: str) -> list[float]:
        """Anthropic has no embeddings endpoint.

        Args:
            text: Ignored.

        Returns:
            Never returns.

        Raises:
            UnsupportedLLMOperationError: Always.
        """
        del text
        raise UnsupportedLLMOperationError("AnthropicHttpClient", "embed")


def _content_blocks(body: dict[str, Json]) -> list[dict[str, Json]]:
    return [as_mapping(block) for block in as_list(body.get("content"))]


def _tool_input(body: dict[str, Json]) -> Mapping[str, Json] | None:
    for block in _content_blocks(body):
        if block.get("type") == "tool_use" and block.get("name") == STRUCTURED_TOOL_NAME:
            return as_mapping(block.get("input"))
    return None


def _text_content(body: dict[str, Json]) -> str:
    parts = [
        text
        for block in _content_blocks(body)
        if block.get("type") == "text" and isinstance(text := block.get("text"), str)
    ]
    return "".join(parts)
