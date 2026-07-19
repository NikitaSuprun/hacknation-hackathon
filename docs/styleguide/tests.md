# Tests

- `pytest` + `pytest-xdist`; everything runs offline — warehouse-touching checks
  live in staged scripts (`poe verify-merge`, `poe smoke`), not the suite.
- Golden values over recomputation: assert literal UUIDs, literal SQL, literal
  normalized strings, so drift is visible in the diff.
- Contract tests (`tests/contracts/`) are the CI gate for every frozen seam:
  schemas validate the fixtures, and a deliberately violating payload must fail.
- Test ignores are pre-declared in `ruff.toml` (`S101`, `D`, magic values).
