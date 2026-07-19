# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Typed access into JSON payloads (the one cast seam for API bodies).

Decoded JSON enters as `object` and is narrowed to `Json` shapes here; the
`as_sink` bridge is the single spot where a Json tree becomes a SinkValue
(safe by construction — every Json shape is a valid sink cell, the checkers
just cannot prove it across the invariant recursive aliases).
"""

from typing import cast

from contracts.models import Json, SinkValue


def as_mapping(value: object) -> dict[str, Json]:
    """Narrow a JSON value to an object, or empty when it is not one.

    Args:
        value: Any decoded JSON value.

    Returns:
        The mapping, or {} for non-mappings.
    """
    if isinstance(value, dict):
        return cast("dict[str, Json]", cast("object", value))
    return {}


def as_list(value: object) -> list[Json]:
    """Narrow a JSON value to an array, or empty when it is not one.

    Args:
        value: Any decoded JSON value.

    Returns:
        The list, or [] for non-lists.
    """
    if isinstance(value, list):
        return cast("list[Json]", cast("object", value))
    return []


def as_sink(value: Json) -> SinkValue:
    """Bridge one Json tree into a SinkValue cell.

    Args:
        value: A parsed JSON value.

    Returns:
        The same value, typed for the sink.
    """
    return cast("SinkValue", value)


def get_map(mapping: dict[str, Json], key: str) -> dict[str, Json]:
    """Fetch a nested object field, empty when absent or mistyped.

    Args:
        mapping: The parent object.
        key: The field name.

    Returns:
        The nested mapping, or {}.
    """
    return as_mapping(mapping.get(key))


def get_list(mapping: dict[str, Json], key: str) -> list[Json]:
    """Fetch a nested array field, empty when absent or mistyped.

    Args:
        mapping: The parent object.
        key: The field name.

    Returns:
        The nested list, or [].
    """
    return as_list(mapping.get(key))


def get_str(mapping: dict[str, Json], key: str) -> str | None:
    """Fetch a string field, None when absent or mistyped.

    Args:
        mapping: The parent object.
        key: The field name.

    Returns:
        The string value, or None.
    """
    value = mapping.get(key)
    return value if isinstance(value, str) else None


def get_int(mapping: dict[str, Json], key: str) -> int | None:
    """Fetch an integer field, None when absent or mistyped (bools excluded).

    Args:
        mapping: The parent object.
        key: The field name.

    Returns:
        The integer value, or None.
    """
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
