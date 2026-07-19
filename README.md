# Maschmeyer's Chosen Portfolio

**You don't apply. You get chosen.**

Early-signal deal sourcing for a VC fund: scrape public builder signals (GitHub,
papers, Swiss registry, Hack Nation), resolve them to golden person records,
group people and artifacts into ventures, score against the fund's thesis, and
surface ranked candidates with cited memos and consent-based AI interviews.

The full design and build plan live in [docs/plan/](docs/plan/) — start with
[handover.md](docs/plan/handover.md). Conventions are in [AGENTS.md](AGENTS.md)
and [docs/styleguide/](docs/styleguide/).

## Setup

```sh
uv sync                       # Python 3.13, all dependency groups
uv run pre-commit install     # the gate runs on every commit
uv run poe test
```

Warehouse-backed commands (`poe ddl-apply`, `poe fixtures-load`, `poe smoke`)
need Databricks credentials in `.env` — see
[docs/runbooks/databricks.md](docs/runbooks/databricks.md).
