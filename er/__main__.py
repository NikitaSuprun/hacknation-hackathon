# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""ER CLI: `python -m er run` and `python -m er unmerge`.

`run --fixtures --dry-run` is the zero-credential path: fixture rows, a
scripted LLM, the seeded allocator, and a NullSink. Live runs compose the
warehouse row source, the Databricks sink, and the ai_query LLM client, and
advance the `er` cursor in ops.scrape_state to the max PSR ingested_at.
"""

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Annotated, Final

import typer

from contracts.interfaces import Sink
from contracts.models import Cursor, Json
from er import embeddings, offline
from er.allocator import RandomPersonIdAllocator, allocator_from_links
from er.io import WarehouseRowSource, sink_all
from er.pipeline import ALL_STAGES, ErDeps, ErInputs, ErOutputs, load_inputs, run_pipeline
from er.unmerge import UnmergeOutcome, UnmergeRequest, plan_unmerge
from scrapers.common.log import configure_logging, get_logger
from scrapers.common.sink import DEFAULT_CATALOG, NullSink
from scrapers.common.state import WarehouseStateStore

app: Final[typer.Typer] = typer.Typer(add_completion=False)

STATE_SOURCE: Final[str] = "er"
LIVE_PIPELINE_VERSION: Final[str] = "er-1"
LIVE_EMBEDDING_MODEL: Final[str] = "databricks-gte-large-en"
OFFLINE_EMBEDDING_MODEL: Final[str] = "fixture-fake-embedding"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_stages(stages: str) -> frozenset[int]:
    if not stages.strip():
        return ALL_STAGES
    return frozenset(int(part) for part in stages.split(",") if part.strip())


@dataclass(frozen=True, slots=True)
class _Composition:
    """One resolved run environment."""

    inputs: ErInputs
    deps: ErDeps
    sink: Sink
    live_write: bool


def _compose(*, fixtures: bool, dry_run: bool, catalog: str, train: bool) -> _Composition:
    if fixtures and dry_run:
        inputs = offline.offline_inputs()
        return _Composition(
            inputs=inputs, deps=offline.offline_deps(inputs), sink=NullSink(), live_write=False
        )
    from tools.db import DatabricksSink  # noqa: PLC0415 - live-only import
    from tools.llm import AiQueryLLMClient  # noqa: PLC0415 - live-only import
    from tools.settings import load_databricks_settings  # noqa: PLC0415 - live-only import
    from tools.warehouse import Warehouse  # noqa: PLC0415 - live-only import

    settings = load_databricks_settings()
    warehouse = Warehouse(settings)
    inputs = load_inputs(WarehouseRowSource(warehouse, catalog))
    deps = ErDeps(
        allocator=allocator_from_links(inputs.link_rows, fallback=RandomPersonIdAllocator()),
        llm=AiQueryLLMClient(warehouse),
        clock=_utc_now,
        pipeline_version=LIVE_PIPELINE_VERSION,
        deterministic_splink=not train,
    )
    sink: Sink = NullSink() if dry_run else DatabricksSink(settings, catalog)
    return _Composition(inputs=inputs, deps=deps, sink=sink, live_write=not dry_run)


def _since_filter(inputs: ErInputs, since: str | None) -> ErInputs:
    """Keep only bronze rows ingested at or after the since date."""
    if since is None:
        return inputs
    floor = f"{since}T00:00:00+00:00"

    def keep(rows: list[dict[str, Json]]) -> list[dict[str, Json]]:
        return [row for row in rows if str(row.get("ingested_at") or "") >= floor]

    return replace(
        inputs,
        github_users=keep(inputs.github_users),
        github_commits=keep(inputs.github_commits),
        github_repos=keep(inputs.github_repos),
        arxiv_papers=keep(inputs.arxiv_papers),
        openalex_works=keep(inputs.openalex_works),
        zefix_companies=keep(inputs.zefix_companies),
        zefix_sogc=keep(inputs.zefix_sogc),
        hacknation_people=keep(inputs.hacknation_people),
        hacknation_projects=keep(inputs.hacknation_projects),
    )


def _watermark(inputs: ErInputs, outputs: ErOutputs) -> str | None:
    stamps = [
        str(stamp) for row in inputs.psr_rows if (stamp := row.get("ingested_at")) is not None
    ]
    for produced in outputs.tables.get("silver.person_source_record", []):
        stamp = produced.get("ingested_at")
        if isinstance(stamp, datetime):
            stamps.append(stamp.isoformat())
    return max(stamps) if stamps else None


def _active_link_map(inputs: ErInputs, outputs: ErOutputs) -> dict[str, str]:
    linked: dict[str, str] = {}
    for row in inputs.link_rows:
        if row.get("status") == "active":
            linked[str(row.get("source_record_id"))] = str(row.get("person_id"))
    for produced in outputs.tables.get("silver.person_source_link", []):
        if produced.get("status") == "active":
            linked[str(produced.get("source_record_id"))] = str(produced.get("person_id"))
    return linked


def _add_embeddings(
    inputs: ErInputs, outputs: ErOutputs, deps: ErDeps, *, embedding_model: str
) -> None:
    texts = embeddings.profile_texts_by_person(inputs.psr_rows, _active_link_map(inputs, outputs))
    outputs.tables["gold.person_features"] = embeddings.embedding_rows(
        texts, deps.llm, embedding_model=embedding_model, clock=deps.clock
    )


def _save_cursor(composition: _Composition, catalog: str, outputs: ErOutputs, total: int) -> None:
    """Advance the er cursor after a live write."""
    from tools.settings import load_databricks_settings  # noqa: PLC0415 - live-only import
    from tools.warehouse import Warehouse  # noqa: PLC0415 - live-only import

    watermark = _watermark(composition.inputs, outputs)
    if watermark is None:
        return
    warehouse = Warehouse(load_databricks_settings())
    store = WarehouseStateStore(warehouse, composition.sink, catalog, clock=_utc_now)
    store.save(
        STATE_SOURCE,
        Cursor(source=STATE_SOURCE, state={"watermark": watermark}),
        status="ok",
        error=None,
        items_upserted=total,
    )


@app.command()
def run(  # noqa: PLR0913 - the CLI flag surface # pyright: ignore[reportUnusedFunction] - typer-registered
    *,
    since: str | None = None,
    fixtures: bool = False,
    dry_run: bool = False,
    catalog: str = DEFAULT_CATALOG,
    stages: str = "0,2,3,4,5",
    with_embeddings: bool = False,
    train: bool = False,
) -> None:
    """Run the ER pipeline stages and upsert the produced rows."""
    configure_logging()
    log = get_logger(STATE_SOURCE)
    composition = _compose(fixtures=fixtures, dry_run=dry_run, catalog=catalog, train=train)
    inputs = _since_filter(composition.inputs, since)
    outputs = run_pipeline(inputs, composition.deps, stages=_parse_stages(stages))
    if with_embeddings:
        offline_mode = fixtures and dry_run
        _add_embeddings(
            inputs,
            outputs,
            composition.deps,
            embedding_model=OFFLINE_EMBEDDING_MODEL if offline_mode else LIVE_EMBEDDING_MODEL,
        )
    results = sink_all(composition.sink, outputs.tables)
    total = 0
    for table in sorted(outputs.tables):
        count = len(outputs.tables[table])
        total += count
        typer.echo(f"{table}: {count} rows")
    for conflict in outputs.conflicts:
        log.info(
            "survivorship conflict",
            person_id=conflict.person_id,
            field=conflict.field,
            values=list(conflict.values),
        )
    if composition.live_write:
        _save_cursor(composition, catalog, outputs, total)
    typer.echo(f"total: {total} rows across {len(results)} tables")


def _unmerge_plan(request: UnmergeRequest, catalog: str, *, offline_mode: bool) -> UnmergeOutcome:
    if offline_mode:
        return plan_unmerge(
            request,
            offline.offline_inputs().link_rows,
            clock=offline.frozen_clock,
            pipeline_version=offline.PIPELINE_VERSION,
            catalog=catalog,
        )
    from tools.settings import load_databricks_settings  # noqa: PLC0415 - live-only import
    from tools.warehouse import Warehouse  # noqa: PLC0415 - live-only import

    warehouse = Warehouse(load_databricks_settings())
    links = WarehouseRowSource(warehouse, catalog).rows("silver.person_source_link")
    return plan_unmerge(
        request, links, clock=_utc_now, pipeline_version=LIVE_PIPELINE_VERSION, catalog=catalog
    )


def _execute_unmerge(outcome: UnmergeOutcome, catalog: str) -> None:
    from tools.db import DatabricksSink  # noqa: PLC0415 - live-only import
    from tools.settings import load_databricks_settings  # noqa: PLC0415 - live-only import
    from tools.warehouse import Warehouse  # noqa: PLC0415 - live-only import

    settings = load_databricks_settings()
    sink_all(
        DatabricksSink(settings, catalog),
        {"silver.person_source_link": [outcome.retracted_link, outcome.corrective_link]},
    )
    warehouse = Warehouse(settings)
    for statement in outcome.invalidation_statements:
        warehouse.execute(statement)


@app.command()
def unmerge(  # noqa: PLR0913 - the CLI flag surface # pyright: ignore[reportUnusedFunction] - typer-registered
    *,
    link_id: Annotated[str, typer.Option("--link-id")],
    to_person: Annotated[str, typer.Option("--to-person")],
    reason: Annotated[str, typer.Option("--reason")],
    reviewer_note: str = "",
    actor: str = "analyst",
    fixtures: bool = False,
    dry_run: bool = False,
    catalog: str = DEFAULT_CATALOG,
) -> None:
    """Retract one wrong link and repoint its PSR to the correct person."""
    configure_logging()
    request = UnmergeRequest(
        link_id=link_id,
        to_person_id=to_person,
        reason=reason,
        reviewer_note=reviewer_note,
        actor=actor,
    )
    outcome = _unmerge_plan(request, catalog, offline_mode=fixtures and dry_run)
    if dry_run:
        typer.echo(
            json.dumps(
                {
                    "source_record_id": outcome.source_record_id,
                    "from_person": outcome.affected_person_ids[0],
                    "to_person": outcome.affected_person_ids[1],
                },
                sort_keys=True,
            )
        )
        for statement in outcome.invalidation_statements:
            typer.echo(statement)
        return
    _execute_unmerge(outcome, catalog)
    typer.echo(f"unmerged {outcome.source_record_id} -> {to_person}")


if __name__ == "__main__":
    app()
