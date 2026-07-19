# Engineering standards & pre-commit gate

A strict, opinionated toolchain and convention set — the gate is what keeps parallel work consistent and self-documenting. Config files live at the repo root: `.pre-commit-config.yaml`, `ruff.toml`, `pyrightconfig.json`, `ty.toml`, `pyproject.toml`, `poe_tasks.toml`, plus `docs/styleguide/`, `AGENTS.md`, and a `scripts/pre-commit/` folder of custom hooks. WS0 sets this up Day 0 so every workstream inherits the gate from commit one.

## Toolchain

- **Python 3.13**; **`uv`** + committed `uv.lock` (dependency-groups per subpackage, pinned; `[tool.uv] default-groups="all"`); **`poe`** (poethepoet) task runner; **`pytest` + `pytest-xdist`** (parallel).
- **TS/React** (Lovable + edge functions): project default + ESLint + Prettier + `tsc --strict`.

## `.pre-commit-config.yaml` (starting point)

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
      - id: check-merge-conflict
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.17
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: ty
        name: ty check
        entry: uv run ty check
        language: system
        types: [python]
        pass_filenames: false
      - id: basedpyright
        name: basedpyright (strict)
        entry: uv run basedpyright
        language: system
        types: [python]
        pass_filenames: false
      - id: pydoclint
        name: pydoclint (docstring matches signature)
        entry: uv run pydoclint
        language: system
        types: [python]
      # Suppressions must carry a reason: "<directive>: <CODE> - <reason>".
      - id: noqa-needs-reason
        name: "# noqa must be: # noqa: <CODE> - <reason>"
        language: pygrep
        entry: '(?i)#\s*noqa(?!:\s*[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*\s+-\s+\S)'
        types: [python]
      - id: type-ignore-needs-reason
        name: "# type:/pyright: ignore must carry a reason"
        language: pygrep
        entry: '(?i)#\s*(?:type|pyright):\s*ignore(?!(?:\[[^\]]*\])?\s+-\s+\S)'
        types: [python]
      - id: constants-final
        name: "module constants must be annotated Final[...]"
        entry: uv run python scripts/pre-commit/check_constants_final.py
        language: system
        types: [python]
      - id: max-nesting
        name: "functions must not nest control-flow more than 3 deep"
        entry: uv run python scripts/pre-commit/check_max_nesting.py
        language: system
        types: [python]
      - id: license-header
        name: "license-header (proprietary copyright on every .py)"
        entry: uv run python scripts/pre-commit/add_license_header.py
        language: system
        types: [python]
```

## Ruff `select` set (`ruff.toml`, `target-version = "py313"`, pydocstyle google)

`F,E,W,I,N,UP,ANN,B,A,C4,PIE,PT,RET,SIM,ARG,PTH,TC,PGH,PL,PERF,FURB,RUF,BLE,SLF,DTZ,TRY,ISC,S,FBT,RSE,TID,G,LOG,ASYNC,D,TD` — bundles docstrings (`D`, google), full annotations (`ANN`), complexity/refactor limits (`PL`), security (`S`, bandit), tz-aware datetimes (`DTZ`), TODO-must-link-issue (`TD`). Per-file ignores for tests (`S101,S105,S106,D,PLR2004,SLF001,PLR0913`).

## Type-checking (dual, strict)

- **basedpyright** strict: `reportExplicitAny=error`, `reportUnannotatedClassAttribute=error`, `reportInvalidCast=error`, `reportImplicitRelativeImport=error`, `reportIgnoreCommentWithoutRule=error`.
- **ty** promotes likely-bug diagnostics to errors: `possibly-unresolved-reference`, `possibly-missing-import`, `possibly-missing-attribute`, `division-by-zero`, `redundant-cast`, `unused-ignore-comment`.
- **No `Any`** in our annotations; **parametrized generics required** — `dict[str, int]`, `list[Foo]`, `set[str]`, never bare `dict`/`list` (strict pyright flags bare generics). This is the "write out the internal types" rule, machine-enforced.

## Types & value objects

Full annotations everywhere; frozen `@dataclass(frozen=True, slots=True)` value objects in a sibling `models.py` (not `dataclasses.py` — `ruff A005`); **no default field values** on value types; stateful classes declare instance attrs in a class-level block with `Final[T]` for set-once; `Literal` aliases for closed sets; semantic unit types (`timedelta`, `Decimal`), not `_ms`/`_seconds` numbers; test optionals with `is None`/`is not None`, never truthiness; casts are a last resort (launder through an `object` seam); expected recoverable outcomes returned as `Status`/`StatusOr` values, not raised.

## Docstrings & comments

Google docstrings — one line for one-liners, full `Args`/`Returns`/`Raises` otherwise, **types only in the signature** (`pydoclint`: `arg-type-hints-in-docstring=false`, `check-return-types=false`, `skip-checking-private-functions=true`). Comments are **minimal, why-only, forward-looking, ASCII** — the code is self-documenting, never explain the same thing twice; a file header states *why the file exists*, not its mechanics; rationale/history goes in the commit message; TODOs link a tracked issue (`# TODO(#NN): ...`).

## Functions

Cap control-flow nesting at **3 levels** (`if`/`for`/`while`/`with`/`try`/`match`); a 4th means extract a named helper. Keep top-level callers at orchestration altitude (push metric/log bookkeeping into `record_*` helpers).

## Config & data

Layered TOML deep-merged into frozen `Settings` dataclasses (no field defaults, no env-var fallbacks — fail fast); secrets in `.env` only; SQL lives in `*.sql` files run by name (matches the DDL layout).

## Git

Terse imperative commit subjects, **no `feat:`/`fix:` prefixes**, **no AI watermark / no `Co-Authored-By`** in commits or PR bodies; one coherent reviewable slice per commit.

## Documentation & diagrams

README/doc prose must read human-written, not AI boilerplate — draft with an external model given real background (e.g. **`codex`**), then edit to a terse, purpose-first voice defined in `docs/styleguide/`. **All diagrams are Mermaid** (` ```mermaid ` fenced), never hand-drawn ASCII. Keep an `AGENTS.md` + `docs/styleguide/` (naming, docstrings, comments, functions, types, tests, config, git pages) so every parallel session/agent writes the same way.

## License compliance

`pip-licenses` → `THIRD_PARTY_LICENSES.md` (poe `licenses` task + banner), regenerated on dependency change via `.github/workflows/licenses.yml`. Permissive-only dependency allowlist (MIT/BSD/Apache-2.0/ISC/MPL-2.0); denylist GPL/AGPL/SSPL and non-commercial/"source-available" terms; MPL/LGPL tracked. Concrete swap: **RapidFuzz (MIT)**, not python-Levenshtein (GPL). Repo license `LicenseRef-Proprietary` + a per-file proprietary header hook. Goal: never a copyleft obligation to open-source our code, never a non-commercial term in the graph.

## CI

`.github/workflows/ci.yml` runs the full gate (`uv run pre-commit run --all-files`) + tests on every PR; `licenses.yml` regenerates the inventory; dependabot for updates. **Acceptance**: gate green on the skeleton before any workstream starts.
