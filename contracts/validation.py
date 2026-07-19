# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Validate semi-structured payloads against the frozen JSON Schemas."""

import json
from collections.abc import Callable, Iterator
from functools import cache
from pathlib import Path
from typing import Final, Protocol, cast

from jsonschema.exceptions import ValidationError
from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import Schema, SchemaRegistry

from contracts.models import Json


class _ValidatorLike(Protocol):
    """The one validator method we use, typed for parsed-JSON instances."""

    def iter_errors(self, instance: Json) -> Iterator[ValidationError]:
        """Yield every violation of the schema by the instance."""
        ...


# The jsonschema stubs type schemas/instances with Any-laced recursive
# aliases; these two casts are the single laundering seam for that.
_CHECK_SCHEMA: Final[Callable[[dict[str, Json]], None]] = cast(
    "Callable[[dict[str, Json]], None]", Draft202012Validator.check_schema
)

SCHEMA_DIR: Final[Path] = Path(__file__).resolve().parent / "schemas"

_SCHEMA_BASE_URI: Final[str] = "https://dealflow.internal/schemas/"
_META_KEYS: Final[frozenset[str]] = frozenset({"$schema", "$id"})

PAYLOAD_SCHEMAS: Final[tuple[str, str, str, str, str]] = (
    "evidence",
    "breakdown",
    "memo",
    "ideal",
    "interview",
)


def schema_path(name: str) -> Path:
    """Path of one schema file.

    Args:
        name: Schema name without extension (e.g. "memo").

    Returns:
        The path under contracts/schemas.
    """
    return SCHEMA_DIR / f"{name}.schema.json"


def load_schema(name: str) -> dict[str, Json]:
    """Load one schema document.

    Args:
        name: Schema name without extension.

    Returns:
        The parsed schema.

    Raises:
        TypeError: If the schema file is not a JSON object.
    """
    parsed: Json = json.loads(schema_path(name).read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError(name)
    return parsed


def bundled_schema(name: str) -> dict[str, Json]:
    """One payload schema with cross-file $refs inlined.

    Validation resolves `$ref`s through the registry, but consumers that only
    see the JSON text — notably LLM structured-output APIs — cannot fetch
    another file, and silently invent the referenced shape. Inlining keeps
    the single source of truth in contracts/schemas.

    Args:
        name: The payload schema name.

    Returns:
        A self-contained schema.
    """
    return _inline_refs(load_schema(name))


def _inline_refs(node: Json) -> dict[str, Json]:
    inlined = _walk(node)
    return inlined if isinstance(inlined, dict) else {}


def _walk(node: Json) -> Json:
    if isinstance(node, list):
        return [_walk(item) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith(_SCHEMA_BASE_URI):
        target = load_schema(ref.removeprefix(_SCHEMA_BASE_URI).removesuffix(".schema.json"))
        body = {key: value for key, value in target.items() if key not in _META_KEYS}
        return _walk(cast("Json", body))
    return {key: _walk(value) for key, value in node.items()}


def check_schema(name: str) -> None:
    """Raise if the schema document itself is not valid Draft 2020-12.

    Args:
        name: Schema name without extension.
    """
    _CHECK_SCHEMA(load_schema(name))


@cache
def _registry() -> SchemaRegistry:
    registry: SchemaRegistry = Registry()
    for name in PAYLOAD_SCHEMAS:
        contents: Schema = load_schema(name)
        resource: Resource[Schema] = Resource.from_contents(contents)
        registry = resource @ registry
    return registry


def validator_for(name: str) -> _ValidatorLike:
    """Build a validator with cross-schema references resolvable.

    Args:
        name: Schema name without extension.

    Returns:
        A Draft 2020-12 validator for the schema.
    """
    return cast("_ValidatorLike", Draft202012Validator(load_schema(name), registry=_registry()))


def payload_errors(name: str, payload: Json) -> list[str]:
    """Collect human-readable validation errors for a payload.

    Args:
        name: Schema name without extension.
        payload: The parsed JSON value to check.

    Returns:
        One message per violation; empty when the payload conforms.
    """
    validator = validator_for(name)
    return [
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(payload)
    ]
