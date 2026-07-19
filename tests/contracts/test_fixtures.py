# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Fixture contract tests: committed JSONL matches the builder; validator bites."""

import json
import shutil
from pathlib import Path

from fixtures.build import DATA_DIR, write_jsonl
from fixtures.fake_embedding import cosine, fake_embedding
from fixtures.validate import validate


def test_committed_fixtures_match_builder(tmp_path: Path) -> None:
    rebuilt_dir = tmp_path / "data"
    write_jsonl(rebuilt_dir)
    committed = sorted(p.name for p in DATA_DIR.glob("*.jsonl"))
    rebuilt = sorted(p.name for p in rebuilt_dir.glob("*.jsonl"))
    assert committed == rebuilt
    for name in committed:
        assert (DATA_DIR / name).read_bytes() == (rebuilt_dir / name).read_bytes(), name


def test_validator_passes_on_committed_fixtures() -> None:
    assert validate() == []


def _mutate(tmp_path: Path, table: str, row_index: int, column: str, value: object) -> Path:
    mutated_dir = tmp_path / "mutated"
    shutil.copytree(DATA_DIR, mutated_dir)
    path = mutated_dir / f"{table}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    rows[row_index][column] = value
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + "\n",
        encoding="utf-8",
    )
    return mutated_dir


def test_validator_catches_dangling_fk(tmp_path: Path) -> None:
    mutated = _mutate(tmp_path, "gold.venture_member", 0, "person_id", "not-a-person")
    assert any("dangling reference" in e for e in validate(mutated))


def test_validator_catches_second_active_link(tmp_path: Path) -> None:
    mutated = _mutate(tmp_path, "silver.person_source_link", 11, "status", "active")
    assert any("active links" in e for e in validate(mutated))


def test_validator_catches_bad_enum(tmp_path: Path) -> None:
    mutated = _mutate(tmp_path, "gold.venture", 0, "status", "funded")
    assert any("invalid value" in e for e in validate(mutated))


def test_validator_catches_non_unit_embedding(tmp_path: Path) -> None:
    mutated = _mutate(tmp_path, "gold.ideal_candidate", 0, "embedding", [1.0] * 1024)
    assert any("not unit-norm" in e for e in validate(mutated))


def test_fake_embedding_correlates_by_shared_tokens() -> None:
    robotics = fake_embedding("robotic grasping manipulation")
    ideal = fake_embedding("robotics manipulation grasping ideal")
    databases = fake_embedding("database query optimization")
    assert cosine(robotics, robotics) > 0.999
    assert cosine(robotics, ideal) > cosine(databases, ideal)
    assert fake_embedding("same text") == fake_embedding("same text")
