# Naming

- Modules: short, lowercase, no underscores unless needed; value objects live in a
  sibling `models.py` (never `dataclasses.py` — shadows the stdlib, ruff A005).
- Functions/variables: `snake_case`, verbs for functions, nouns for values.
- Module constants: `UPPER_CASE` and annotated `Final[...]` (hook-enforced).
- No abbreviations the next reader has to decode; spell out `publication`, not `pub`.
- SQL files are numbered by layer (`00_catalog … 50_views`) and run in name order.
