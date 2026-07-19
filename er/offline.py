# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Credential-free ER composition: fixtures in, scripted decisions, no network.

Everything nondeterministic is pinned: the clock is the fixture clock, the
allocator lands clusters on the committed persona ids, and the LLM is a
script keyed by prompt tags (adjudication verdicts and headlines mirroring
the fixture narrative). `--fixtures --dry-run` in er.__main__ composes from
here, which is what keeps the CI path free of any secret.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Final

from contracts.models import Json, LLMResponse
from er import adjudicate
from er.allocator import RandomPersonIdAllocator, allocator_from_links
from er.io import FixtureRowSource
from er.pipeline import ErDeps, ErInputs, load_inputs
from er.survivorship import headline_tag
from fixtures import build as fixture_build
from fixtures.fake_embedding import fake_embedding
from scrapers.common.jsonutil import get_str

FIXTURE_DATA_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "fixtures" / "data"
OFFLINE_MODEL: Final[str] = "scripted-offline"
PIPELINE_VERSION: Final[str] = fixture_build.PIPELINE_VERSION
FROZEN_NOW: Final[datetime] = datetime.fromisoformat(fixture_build.T_UPDATED)

WEI_A_PAIR_ID: Final[str] = adjudicate.pair_id(
    fixture_build.PSR_WEI_A_GITHUB, fixture_build.PSR_WEI_A_OPENALEX
)
JONAS_PAIR_ID: Final[str] = adjudicate.pair_id(
    fixture_build.PSR_JONAS_GITHUB, fixture_build.PSR_JONAS_ZEFIX
)
WEI_HN_A_PAIR_ID: Final[str] = adjudicate.pair_id(
    fixture_build.PSR_WEI_A_OPENALEX, fixture_build.PSR_WEI_HN
)
WEI_HN_B_PAIR_ID: Final[str] = adjudicate.pair_id(
    fixture_build.PSR_WEI_B_OPENALEX, fixture_build.PSR_WEI_HN
)
WEI_HN_GH_PAIR_ID: Final[str] = adjudicate.pair_id(
    fixture_build.PSR_WEI_A_GITHUB, fixture_build.PSR_WEI_HN
)
LENA_HN_ZEFIX_PAIR_ID: Final[str] = adjudicate.pair_id(
    fixture_build.PSR_LENA_ZEFIX, fixture_build.PSR_LENA_HN
)
LENA_HN_OPENALEX_PAIR_ID: Final[str] = adjudicate.pair_id(
    fixture_build.PSR_LENA_OPENALEX, fixture_build.PSR_LENA_HN
)
LENA_HN_GITHUB_PAIR_ID: Final[str] = adjudicate.pair_id(
    fixture_build.PSR_LENA_GITHUB, fixture_build.PSR_LENA_HN
)
# Mirrors the WeiA fixture link evidence byte-for-byte.
WEI_A_VERDICT: Final[dict[str, Json]] = {
    "verdict": "match",
    "rationale": "Same org, same robotics focus, login matches name",
    "fields_supporting": ["org_norm", "keywords", "country_code"],
}
JONAS_VERDICT: Final[dict[str, Json]] = {
    "verdict": "no_match",
    "rationale": "Berlin software developer versus Zug corporate advisor",
    "fields_supporting": [],
}
WEI_HN_A_VERDICT: Final[dict[str, Json]] = {
    "verdict": "match",
    "rationale": "Same ETH robot-learning Wei; the hackathon profile mirrors the scholar",
    "fields_supporting": ["name_norm", "org_norm", "keywords"],
}
WEI_HN_B_VERDICT: Final[dict[str, Json]] = {
    "verdict": "no_match",
    "rationale": "Name twin only; the ETH hackathon builder is not the EPFL theorist",
    "fields_supporting": [],
}
LENA_HN_VERDICT: Final[dict[str, Json]] = {
    "verdict": "match",
    "rationale": "Same ETH grasping founder across the hackathon and registry records",
    "fields_supporting": ["name_norm", "org_norm", "country_code"],
}


def frozen_clock() -> datetime:
    """The fixture clock: always T_UPDATED.

    Returns:
        The frozen timestamp.
    """
    return FROZEN_NOW


def _verdict_response(verdict: dict[str, Json]) -> LLMResponse:
    return LLMResponse(
        text=json.dumps(verdict, ensure_ascii=False, sort_keys=True),
        parsed=verdict,
        model=OFFLINE_MODEL,
    )


def scripted_responses(inputs: ErInputs) -> dict[str, LLMResponse]:
    """The offline LLM script: canned verdicts plus fixture headlines.

    Args:
        inputs: The fixture inputs (headlines come from silver.person rows).

    Returns:
        Responses keyed by prompt tag.
    """
    responses: dict[str, LLMResponse] = {
        f"TASK:adjudicate pair={WEI_A_PAIR_ID}": _verdict_response(WEI_A_VERDICT),
        f"TASK:adjudicate pair={JONAS_PAIR_ID}": _verdict_response(JONAS_VERDICT),
        f"TASK:adjudicate pair={WEI_HN_A_PAIR_ID}": _verdict_response(WEI_HN_A_VERDICT),
        f"TASK:adjudicate pair={WEI_HN_B_PAIR_ID}": _verdict_response(WEI_HN_B_VERDICT),
        f"TASK:adjudicate pair={WEI_HN_GH_PAIR_ID}": _verdict_response(WEI_HN_A_VERDICT),
        f"TASK:adjudicate pair={LENA_HN_ZEFIX_PAIR_ID}": _verdict_response(LENA_HN_VERDICT),
        f"TASK:adjudicate pair={LENA_HN_OPENALEX_PAIR_ID}": _verdict_response(LENA_HN_VERDICT),
        f"TASK:adjudicate pair={LENA_HN_GITHUB_PAIR_ID}": _verdict_response(LENA_HN_VERDICT),
    }
    for row in inputs.person_rows:
        person_id = get_str(row, "person_id")
        headline = get_str(row, "headline")
        if person_id is not None and headline is not None:
            responses[headline_tag(person_id)] = LLMResponse(
                text=headline, parsed=None, model=OFFLINE_MODEL
            )
    return responses


def offline_inputs(data_dir: Path = FIXTURE_DATA_DIR) -> ErInputs:
    """Load the pipeline inputs from the committed fixtures.

    Args:
        data_dir: The fixture data directory.

    Returns:
        The assembled inputs.
    """
    return load_inputs(FixtureRowSource(data_dir))


def offline_deps(inputs: ErInputs) -> ErDeps:
    """Compose fully deterministic pipeline dependencies.

    Args:
        inputs: The fixture inputs (the allocator seeds from their links).

    Returns:
        The dependencies for a credential-free run.
    """
    from tools.llm import ScriptedLLMClient  # noqa: PLC0415 - keep httpx off the import path

    llm = ScriptedLLMClient(
        scripted_responses(inputs),
        embedder=fake_embedding,
        default=LLMResponse(text="", parsed=None, model=OFFLINE_MODEL),
    )
    allocator = allocator_from_links(inputs.link_rows, fallback=RandomPersonIdAllocator())
    return ErDeps(
        allocator=allocator,
        llm=llm,
        clock=frozen_clock,
        pipeline_version=PIPELINE_VERSION,
        deterministic_splink=True,
    )
