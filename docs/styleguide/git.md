# Git

- Terse imperative subjects; no `feat:`/`fix:` prefixes; one coherent reviewable
  slice per commit.
- No AI watermark, no `Co-Authored-By` in commits or PR bodies.
- Rationale goes in the commit body, not in code comments.
- Run `uv run poe gate` before pushing; CI runs the same gate.
- After the Day-1 contract freeze, schema/interface changes are additive-only.
