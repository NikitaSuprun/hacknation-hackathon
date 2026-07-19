# Institution seed (ROR-derived, CC0)

`ror_seed.jsonl` maps every known spelling of an institution (labels, aliases,
acronyms, multilingual names) to its canonical ROR record. The data comes from
the [Research Organization Registry](https://ror.org) and is CC0-licensed, so
shipping it in-repo is clean.

Consumers go through `tools.institutions` (`resolve`, `org_norm`); nothing
reads this file directly.

Regenerate after editing `seed_queries.txt`:

```sh
uv run python -m tools.build_institutions
```

For full worldwide coverage later, download an official ROR data dump
(v2 JSON, from Zenodo) and run:

```sh
uv run python -m tools.build_institutions --ror-dump path/to/ror-data.json
```
