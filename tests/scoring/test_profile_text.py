# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Domain-fit: the robotics founder tops the robotics ideal; edits reorder."""

from contracts.models import Json
from fixtures import build
from fixtures.fake_embedding import fake_embedding
from scoring.profile_text import domain_fit, render_ideal_text, render_person_text
from scoring.snapshot import SilverSnapshot


def rankings(ideal_text: str) -> list[tuple[float, str]]:
    ideal = fake_embedding(ideal_text)
    scored = [
        (domain_fit(fake_embedding(text), ideal), person_id)
        for person_id, text in (
            (build.LENA, build.LENA_TEXT),
            (build.WEI_A, build.WEI_A_TEXT),
        )
    ]
    scored.sort(reverse=True)
    return scored


def test_lena_tops_the_robotics_ideal() -> None:
    assert rankings(build.IDEAL_TEXT)[0][1] == build.LENA


def test_editing_the_ideal_toward_simulation_reorders_to_wei() -> None:
    assert rankings("simulation reinforcement learning")[0][1] == build.WEI_A


def test_render_person_text_is_deterministic_and_topical(silver: SilverSnapshot) -> None:
    lena = next(row for row in silver.persons if row["person_id"] == build.LENA)
    projects = [row for row in silver.projects if row["project_id"] == build.GRASP_PROJECT]
    publications = [
        row for row in silver.publications if row["publication_id"] == build.GRASP_PUBLICATION
    ]
    text = render_person_text(lena, projects, publications)
    assert text == render_person_text(lena, projects, publications)
    assert "robotics" in text
    assert "grasping" in text


def test_render_ideal_text_covers_narrative_keywords_sectors() -> None:
    profile: dict[str, Json] = {
        "narrative": "Robotics researcher-founder.",
        "keywords": ["manipulation", "grasping"],
        "sectors": ["robotics"],
        "numeric_features": {},
    }
    text = render_ideal_text(profile)
    assert "robotics" in text
    assert "manipulation" in text
    assert text == render_ideal_text(profile)


def test_domain_fit_is_the_unit_dot_product() -> None:
    vector = fake_embedding("robotic grasping")
    assert domain_fit(vector, vector) == sum(component * component for component in vector)
