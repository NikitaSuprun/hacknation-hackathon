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

## Implementation & technology

### Data sources

Four connectors feed the same warehouse. The GitHub scraper walks recently
created repositories and bisects by creation date to work around the search
API's thousand-result ceiling, then batches commit history and contributor
profiles into GraphQL calls. The papers scraper uses arXiv as its spine and
enriches against OpenAlex. We scrape Hack Nation ourselves, through the two
public JSON endpoints behind the showcase: participants, projects, teams,
pitches and CVs. The Swiss company registry is next; its schema is already in
place.

### The warehouse

Data lands in Databricks: Unity Catalog, Delta tables and a serverless SQL
warehouse. Raw payloads are kept whole in a bronze layer, resolved into silver,
then shaped into the gold tables the application reads. Each write stages a
Parquet file to a volume before running one MERGE. A content hash skips
anything that hasn't changed, so re-running a scrape is cheap. Erasure requests
are enforced inside that MERGE, so a later scrape cannot bring someone back.

### One person, many sources

The same builder shows up as a GitHub login, a paper author and a hackathon
profile. Facts stay attached to those per-source identities rather than to the
person, and the golden `person_id` is a set of links laid over them. Eight
deterministic rules handle the clear matches: ORCID, email, LinkedIn URL, or a
project's repository. Splink scores the rest. Claude, called directly from SQL,
decides the band that stays ambiguous. Since identity exists only as links, a
wrong merge is undone without touching a single fact.

### How we score

Each person gets ten signals computed in SQL, including weighted stars, commit
volume, recency, centrality, citations and school tier. A missing signal stays
null rather than becoming zero. Claude handles the judgements a query cannot:
whether a commit history is any good, whether a product is defensible.
Embeddings do one job, domain fit. They cannot know that MIT outranks KTH or
that 8,200 stars dwarf 82, so prestige and scale stay in the feature layer.
Nine weighted category scores become one ranking, and changing a weight
re-sorts it in the browser.

A one-page architecture diagram and the pitch script live in
[presentation/](presentation/).
