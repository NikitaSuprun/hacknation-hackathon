"""T11: profile embeddings - fixture byte-match, domain fit, contract errors."""

import json

import pytest

from er.embeddings import (
    ProfileDimensionError,
    embed_profile,
    embedding_rows,
    render_profile_text,
)
from er.models import psr_view
from er.offline import frozen_clock
from er.pipeline import ErInputs
from fixtures import build as fx
from fixtures.fake_embedding import cosine, fake_embedding
from scrapers.common.jsonutil import get_list
from tests.er.conftest import fixture_rows
from tools.llm import ScriptedLLMClient


def _llm() -> ScriptedLLMClient:
    return ScriptedLLMClient({}, embedder=fake_embedding)


def test_fixture_profile_texts_embed_byte_identically() -> None:
    features = fixture_rows("gold.person_features")
    texts = {str(row["person_id"]): str(row["profile_text"]) for row in features}
    produced = embedding_rows(
        texts, _llm(), embedding_model="fixture-fake-embedding", clock=frozen_clock
    )
    expected_by_person = {str(row["person_id"]): row for row in features}
    for row in produced:
        expected = expected_by_person[str(row["person_id"])]
        assert json.dumps(row["profile_embedding"]) == json.dumps(expected["profile_embedding"])
        assert row["embedding_model"] == expected["embedding_model"]


def test_fischer_tops_domain_fit_against_the_ideal() -> None:
    (ideal,) = fixture_rows("gold.ideal_candidate")
    ideal_vector = [float(v) for v in get_list(ideal, "embedding") if isinstance(v, int | float)]
    fits = {
        str(row["person_id"]): cosine(embed_profile(str(row["profile_text"]), _llm()), ideal_vector)
        for row in fixture_rows("gold.person_features")
    }
    assert max(fits, key=lambda person: fits[person]) == fx.LENA


def test_render_profile_text_is_deterministic(inputs: ErInputs) -> None:
    views = [
        psr_view(row)
        for row in inputs.psr_rows
        if str(row["source_record_id"]) in {fx.PSR_LENA_GITHUB, fx.PSR_LENA_OPENALEX}
    ]
    first = render_profile_text(views)
    second = render_profile_text(list(reversed(views)))
    assert first == second
    assert "robotics" in first


def test_wrong_dimension_raises_typed_error() -> None:
    short = ScriptedLLMClient({}, embedder=lambda _text: [1.0, 0.0])
    with pytest.raises(ProfileDimensionError):
        embed_profile("anything", short)
