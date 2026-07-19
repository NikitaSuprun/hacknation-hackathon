# Functions

- Control-flow nesting is capped at 3 levels (`if`/`for`/`while`/`with`/`try`/`match`);
  a fourth means extract a named helper (hook-enforced).
- Keep top-level callers at orchestration altitude; push metric/log bookkeeping
  into `record_*` helpers.
- Expected recoverable outcomes are returned as values, not raised.
