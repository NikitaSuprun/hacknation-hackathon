# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Typed access into untyped JSON payloads (the one cast seam for API bodies)."""

from typing import cast


def as_mapping(value: object) -> dict[str, object]:
    """Narrow a JSON value to an object, or empty when it is not one.

    Args:
        value: Any decoded JSON value.

    Returns:
        The mapping, or {} for non-mappings.
    """
    if isinstance(value, dict):
        return cast("dict[str, object]", cast("object", value))
    return {}


def as_list(value: object) -> list[object]:
    """Narrow a JSON value to an array, or empty when it is not one.

    Args:
        value: Any decoded JSON value.

    Returns:
        The list, or [] for non-lists.
    """
    if isinstance(value, list):
        return cast("list[object]", cast("object", value))
    return []


def get_map(mapping: dict[str, object], key: str) -> dict[str, object]:
    """Fetch a nested object field, empty when absent or mistyped.

    Args:
        mapping: The parent object.
        key: The field name.

    Returns:
        The nested mapping, or {}.
    """
    return as_mapping(mapping.get(key))


def get_list(mapping: dict[str, object], key: str) -> list[object]:
    """Fetch a nested array field, empty when absent or mistyped.

    Args:
        mapping: The parent object.
        key: The field name.

    Returns:
        The nested list, or [].
    """
    return as_list(mapping.get(key))


def get_str(mapping: dict[str, object], key: str) -> str | None:
    """Fetch a string field, None when absent or mistyped.

    Args:
        mapping: The parent object.
        key: The field name.

    Returns:
        The string value, or None.
    """
    value = mapping.get(key)
    return value if isinstance(value, str) else None


def get_int(mapping: dict[str, object], key: str) -> int | None:
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
