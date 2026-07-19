# Comments

Minimal, why-only, forward-looking, ASCII.

- The code is self-documenting; never explain the same thing twice.
- Rationale and history belong in the commit message, not the code.
- TODOs must link a tracked issue: `# TODO(#NN): ...` (ruff `TD`).
- Suppressions carry a reason: `# noqa: CODE - reason`,
  `# pyright: ignore[rule] - reason` (hook-enforced).
