# Types

Strict basedpyright + ty; both must be green.

- Full annotations everywhere; no `Any`; parametrized generics always
  (`dict[str, int]`, `list[Foo]`, never bare `dict`/`list`).
- Value objects: `@dataclass(frozen=True, slots=True)` in `models.py`, no default
  field values.
- Stateful classes declare instance attributes in a class-level block; `Final[T]`
  for set-once.
- `Literal` aliases for closed sets; semantic unit types (`timedelta`, `Decimal`),
  not `_ms`/`_seconds` numbers.
- Test optionals with `is None` / `is not None`, never truthiness.
- Casts are a last resort — launder through an `object` seam and say why.
