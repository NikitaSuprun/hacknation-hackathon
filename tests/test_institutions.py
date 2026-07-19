# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""ROR-backed institution resolution: every observed spelling, one canonical record."""

import json
from typing import Final

from tools.institutions import SEED_PATH, InstitutionRecord, org_norm, resolve
from tools.norm import org_key

_ETH_ROR: Final[str] = "https://ror.org/05a28rw58"


def test_every_eth_spelling_resolves_to_one_record() -> None:
    spellings = [
        "ETHZ",
        "ETH Zurich",
        "ETH Zürich",
        "Eidgenössische Technische Hochschule Zürich",
        "Swiss Federal Institute of Technology in Zurich",
    ]
    for spelling in spellings:
        record = resolve(spelling)
        assert record is not None, spelling
        assert record.ror_id == _ETH_ROR, spelling
        assert org_norm(spelling) == "eth zurich", spelling


def test_acronyms_resolve_to_full_display_names() -> None:
    assert org_norm("MIT") == "massachusetts institute of technology"
    assert org_norm("KTH") == "kth royal institute of technology"
    assert org_norm("UZH") == "university of zurich"
    assert org_norm("NUS") == "national university of singapore"


def test_unknown_organisations_pass_through_mechanically() -> None:
    assert resolve("GraspLab AG") is None
    assert org_norm("GraspLab AG") == "grasplab"
    assert org_norm("Keller Advisory GmbH") == "keller advisory"


def test_seed_records_are_well_formed() -> None:
    lines = [line for line in SEED_PATH.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) >= 20
    for line in lines:
        record = json.loads(line)
        assert record["ror_id"].startswith("https://ror.org/")
        assert record["name"]
        assert isinstance(record["aliases"], list)


def test_resolution_is_key_normalized() -> None:
    record = resolve("  eth   zürich ")
    assert isinstance(record, InstitutionRecord)
    assert org_key(record.name) == "eth zurich"
