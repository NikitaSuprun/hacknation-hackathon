# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Composition root for the app (the only place app constructors live).

`--fixtures` is the zero-credential demo path: FixtureStore over
fixtures/data, RecordingMailer, and the ScriptedLLMClient (fixture scripts
plus the interview turns). Live mode reads the Databricks .env, serves the
gold views through the warehouse, merges writes through the shared sink, and
delivers mail through Resend when RESEND_API_KEY is set.
"""

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from app.auth import SessionRegistry, resolve_password
from app.interview import EngineDeps, InterviewEngine
from app.outreach import Mailer, RecordingMailer, ResendHttpMailer
from app.rescoring import RescoreDeps, run_interview_rescore
from app.store import DataStore, FixtureStore, WarehouseStore
from contracts.interfaces import LLMClient
from contracts.models import Json, LLMResponse
from fixtures import build
from fixtures.fake_embedding import fake_embedding
from scoring.deps import sequential_id_factory
from scoring.rescore import RescoreOutcome
from scoring.scripted import fixture_scripts
from scrapers.common.sink import DEFAULT_CATALOG
from tools.db import DatabricksSink
from tools.ids import new_random_id
from tools.llm import AiQueryLLMClient, ScriptedLLMClient
from tools.settings import load_databricks_settings
from tools.warehouse import Warehouse

RESEND_KEY_ENV: Final[str] = "RESEND_API_KEY"
OFFLINE_ID_PREFIX: Final[str] = "app-offline"
OFFLINE_INTERVIEW_MODEL: Final[str] = "fixture-interview-1"
LIVE_INTERVIEW_MODEL: Final[str] = "interview-1"
FIXTURE_DATA_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "fixtures" / "data"

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


@dataclass(frozen=True, slots=True)
class AppDeps:
    """Everything the /v1 handlers run against."""

    store: DataStore
    mailer: Mailer
    sessions: SessionRegistry
    engine: InterviewEngine
    llm: LLMClient
    clock: Clock
    id_factory: IdFactory
    base_url: str
    catalog: str
    fixtures: bool


def _scripted_response(text: str, parsed: dict[str, Json] | None) -> LLMResponse:
    return LLMResponse(text=text, parsed=parsed, model="scripted")


def interview_scripts(venture_id: str) -> dict[str, LLMResponse]:
    """The scripted interview turns for one venture (offline mode).

    Args:
        venture_id: The venture the interview is about.

    Returns:
        Responses keyed by prompt tag.
    """
    extracted: dict[str, Json] = {
        "schema_version": 1,
        "education": [{"institution": "ETH Zurich", "degree": "PhD", "field": "Robotics"}],
        "career": [{"organization": "GraspLab AG", "role": "Founder", "start_year": 2026}],
        "team_commitment": {"status": "full_time"},
        "traction_claims": [
            {"metric": "paid_pilots", "value": "3", "as_of": None, "verified": False}
        ],
        "funding_status": {"raised_before": False, "details": None},
    }
    return {
        f"TASK:interview venture={venture_id}": _scripted_response("Thanks, noted.", None),
        f"TASK:interview_extract venture={venture_id}": _scripted_response(
            json.dumps(extracted, sort_keys=True), extracted
        ),
    }


def offline_llm() -> ScriptedLLMClient:
    """The zero-credential LLM: fixture scripts plus the interview turns.

    Returns:
        The scripted client with the deterministic fake embedder.
    """
    scripts: dict[str, LLMResponse] = dict(fixture_scripts())
    scripts.update(interview_scripts(build.GRASP_VENTURE))
    return ScriptedLLMClient(scripts, embedder=fake_embedding)


def _assemble(  # noqa: PLR0913 - the composition root names every seam it wires
    *,
    store: DataStore,
    mailer: Mailer,
    llm: LLMClient,
    clock: Clock,
    id_factory: IdFactory,
    base_url: str,
    catalog: str,
    fixtures: bool,
) -> AppDeps:
    rescore_deps = RescoreDeps(llm=llm, clock=clock, id_factory=id_factory, offline=fixtures)

    def rescore(interview_row: Mapping[str, Json]) -> RescoreOutcome:
        return run_interview_rescore(store, rescore_deps, interview_row)

    engine = InterviewEngine(
        EngineDeps(
            store=store,
            llm=llm,
            rescore=rescore,
            clock=clock,
            id_factory=id_factory,
            model_version=OFFLINE_INTERVIEW_MODEL if fixtures else LIVE_INTERVIEW_MODEL,
        )
    )
    return AppDeps(
        store=store,
        mailer=mailer,
        sessions=SessionRegistry(resolve_password(fixtures=fixtures)),
        engine=engine,
        llm=llm,
        clock=clock,
        id_factory=id_factory,
        base_url=base_url,
        catalog=catalog,
        fixtures=fixtures,
    )


def build_fixture_deps(
    *,
    base_url: str,
    data_dir: Path | None = None,
    clock: Clock | None = None,
    id_factory: IdFactory | None = None,
) -> AppDeps:
    """Compose the zero-credential fixtures app.

    Args:
        base_url: Origin used in emailed links.
        data_dir: Fixture JSONL directory (fixtures/data by default).
        clock: Time source override (tests freeze it).
        id_factory: Id source override (tests make it deterministic).

    Returns:
        The assembled dependencies.
    """
    return _assemble(
        store=FixtureStore(data_dir or FIXTURE_DATA_DIR),
        mailer=RecordingMailer(),
        llm=offline_llm(),
        clock=clock or (lambda: datetime.now(UTC)),
        id_factory=id_factory or sequential_id_factory(OFFLINE_ID_PREFIX),
        base_url=base_url,
        catalog=DEFAULT_CATALOG,
        fixtures=True,
    )


def build_live_deps(*, base_url: str, catalog: str = DEFAULT_CATALOG) -> AppDeps:
    """Compose the warehouse-backed app (fails fast without credentials).

    Args:
        base_url: Origin used in emailed links.
        catalog: Target Unity Catalog.

    Returns:
        The assembled dependencies.
    """
    settings = load_databricks_settings()
    warehouse = Warehouse(settings)
    resend_key = os.environ.get(RESEND_KEY_ENV)
    mailer: Mailer = ResendHttpMailer(resend_key) if resend_key else RecordingMailer()
    return _assemble(
        store=WarehouseStore(warehouse, DatabricksSink(settings, catalog), catalog),
        mailer=mailer,
        llm=AiQueryLLMClient(warehouse),
        clock=lambda: datetime.now(UTC),
        id_factory=new_random_id,
        base_url=base_url,
        catalog=catalog,
        fixtures=False,
    )
