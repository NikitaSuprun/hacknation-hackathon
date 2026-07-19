# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""T10 golden: person_connection edges byte-match the fixtures; decay behaves."""

from datetime import datetime

from contracts.models import Json
from er.connections import build_connections, decay
from er.pipeline import ErOutputs
from tests.er.conftest import fixture_lines, render


def test_connection_rows_reproduce_fixture_bytes(scratch_outputs: ErOutputs) -> None:
    produced = scratch_outputs.tables["silver.person_connection"]
    assert [render(row) for row in produced] == fixture_lines("silver.person_connection")


def test_edge_ordering_invariant(scratch_outputs: ErOutputs) -> None:
    for row in scratch_outputs.tables["silver.person_connection"]:
        assert str(row["person_a_id"]) < str(row["person_b_id"])


def test_decay() -> None:
    assert decay(0) == 1.0
    assert decay(365) == 1.0
    assert decay(730) == 0.5 ** (730 / 365.0)


def test_co_officer_edge_from_synthetic_registry() -> None:
    def clock() -> datetime:
        return datetime.fromisoformat("2026-07-15T09:00:00+00:00")

    officers: list[dict[str, Json]] = [
        {
            "officer_id": "o1",
            "company_id": "company-1",
            "source_record_id": "psr-a",
            "registered_at": "2024-01-10",
            "deregistered_at": None,
        },
        {
            "officer_id": "o2",
            "company_id": "company-1",
            "source_record_id": "psr-b",
            "registered_at": "2024-02-20",
            "deregistered_at": None,
        },
    ]
    links = {"psr-a": "person-b", "psr-b": "person-a"}
    rows = build_connections([], [], officers, [], links, clock=clock)
    (edge,) = rows
    assert edge["connection_type"] == "co_officer"
    assert edge["person_a_id"] == "person-a"
    assert edge["person_b_id"] == "person-b"
    assert edge["evidence"] == ["company-1"]
    # Registered ~2.4 years before the clock: the yearly halving applies.
    age_days = (clock().date() - datetime.fromisoformat("2024-02-20").date()).days
    assert edge["weight"] == round(0.5 ** (age_days / 365.0), 4)
