# AGENTS

Read these before writing code or planning — they are how this project is designed and how we write here:

- [docs/plan/handover.md](docs/plan/handover.md) — **read first**: confirmed decisions, verified facts (with sources), open items. Orients you without re-exploring.
- [docs/plan/README.md](docs/plan/README.md) — scope, architecture, and the full document index.
- [docs/plan/reference/engineering-standards.md](docs/plan/reference/engineering-standards.md) — toolchain + the pre-commit gate that keeps the codebase consistent and self-documenting.

The build is split into parallel workstreams under [docs/plan/workstreams/](docs/plan/workstreams/) (start with `ws0-platform-and-contracts.md`), each a checklist with acceptance criteria. Design detail lives in [docs/plan/reference/](docs/plan/reference/).

## Non-negotiables

- Contract-first: after the Day-1 freeze, schema/interface changes are additive-only. Build against `dealflow_dev` fixtures.
- Types: full annotations, no `Any`, parametrized generics (`dict[str, int]`, never bare `dict`); strict `basedpyright` + `ty`.
- Comments: minimal, why-only, ASCII; the code is self-documenting. Google docstrings (`pydoclint`).
- Diagrams: Mermaid only. Docs: human-voiced, not AI boilerplate.
- Git: terse imperative subjects, no `feat:`/`fix:` prefixes, no AI watermark / `Co-Authored-By`.
- Run everything through `uv` / `poe`; `uv run pre-commit run --all-files` before pushing.
- Licensing: permissive deps only (no GPL/AGPL/SSPL); ship only CC0/CC-BY/public-register data files.
