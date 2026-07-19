# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Validate semi-structured payloads against the frozen JSON Schemas."""

import json
from functools import cache
from pathlib import Path
from typing import Final, cast

from jsonschema.protocols import Validator
from jsonschema.validators import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import Schema, SchemaRegistry

SCHEMA_DIR: Final[Path] = Path(__file__).resolve().parent / "schemas"

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


def load_schema(name: str) -> dict[str, object]:
    """Load one schema document.

    Args:
        name: Schema name without extension.

    Returns:
        The parsed schema.

    Raises:
        TypeError: If the schema file is not a JSON object.
    """
    parsed: object = json.loads(schema_path(name).read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError(name)
    return cast("dict[str, object]", parsed)


def check_schema(name: str) -> None:
    """Raise if the schema document itself is not valid Draft 2020-12.

    Args:
        name: Schema name without extension.
    """
    schema: Schema = load_schema(name)
    Draft202012Validator.check_schema(schema)  # pyright: ignore[reportUnknownMemberType] - jsonschema classmethod is loosely typed


@cache
def _registry() -> SchemaRegistry:
    registry: SchemaRegistry = Registry()
    for name in PAYLOAD_SCHEMAS:
        contents: Schema = load_schema(name)
        resource: Resource[Schema] = Resource.from_contents(contents)
        registry = resource @ registry
    return registry


def validator_for(name: str) -> Validator:
    """Build a validator with cross-schema references resolvable.

    Args:
        name: Schema name without extension.

    Returns:
        A Draft 2020-12 validator for the schema.
    """
    return Draft202012Validator(load_schema(name), registry=_registry())


def payload_errors(name: str, payload: object) -> list[str]:
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
        for error in validator.iter_errors(payload)  # pyright: ignore[reportArgumentType] - dynamic JSON cannot satisfy the stub's recursive alias
    ]
