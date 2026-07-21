"""Regenerate data/institutions/ror_seed.jsonl from the ROR registry (CC0).

Default mode queries the free ROR REST API for each name in
data/institutions/seed_queries.txt; `--ror-dump` processes a downloaded
official data dump instead (v2 JSON), keeping every education organisation -
the path to full worldwide coverage without changing any consumer.
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Final

from contracts.models import Json

_DATA_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "data" / "institutions"
QUERIES_PATH: Final[Path] = _DATA_DIR / "seed_queries.txt"
SEED_PATH: Final[Path] = _DATA_DIR / "ror_seed.jsonl"
EXTRA_ALIASES_PATH: Final[Path] = _DATA_DIR / "extra_aliases.json"

_API: Final[str] = "https://api.ror.org/v2/organizations"
_POLITE_DELAY_SECONDS: Final[float] = 0.5


def _names_of(item: dict[str, Json]) -> tuple[str, list[Json]]:
    """Split a ROR names[] block into (display name, other spellings)."""
    display = ""
    aliases: list[Json] = []
    names = item.get("names")
    if not isinstance(names, list):
        return display, aliases
    for entry in names:
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        kinds = entry.get("types")
        if not isinstance(value, str) or not isinstance(kinds, list):
            continue
        if "ror_display" in kinds:
            display = value
        else:
            aliases.append(value)
    return display, aliases


def _country_of(item: dict[str, Json]) -> str | None:
    locations = item.get("locations")
    if isinstance(locations, list) and locations and isinstance(locations[0], dict):
        details = locations[0].get("geonames_details")
        if isinstance(details, dict):
            code = details.get("country_code")
            if isinstance(code, str):
                return code
    return None


def _seed_record(item: dict[str, Json]) -> dict[str, Json] | None:
    """Convert one ROR item into a seed line (None when malformed)."""
    ror_id = item.get("id")
    display, aliases = _names_of(item)
    if not isinstance(ror_id, str) or not display:
        return None
    types = item.get("types")
    record: dict[str, Json] = {
        "ror_id": ror_id,
        "name": display,
        "country": _country_of(item),
        "types": types if isinstance(types, list) else [],
        "aliases": aliases,
    }
    return record


def _fetch_items(query: str) -> list[dict[str, Json]]:
    url = f"{_API}?query={urllib.parse.quote(query)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        payload: Json = json.load(response)
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _is_education(item: dict[str, Json]) -> bool:
    types = item.get("types")
    return isinstance(types, list) and "education" in types


def _pick(items: list[dict[str, Json]]) -> dict[str, Json] | None:
    for item in items:
        if _is_education(item):
            return item
    return items[0] if items else None


def _records_from_api() -> list[dict[str, Json]]:
    records: list[dict[str, Json]] = []
    for query in QUERIES_PATH.read_text(encoding="utf-8").splitlines():
        name = query.strip()
        if not name or name.startswith("#"):
            continue
        picked = _pick(_fetch_items(name))
        record = _seed_record(picked) if picked is not None else None
        if record is None:
            sys.stderr.write(f"NO MATCH  {name}\n")
        else:
            sys.stdout.write(f"{record['ror_id']}  {record['name']}  <-  {name}\n")
            records.append(record)
        time.sleep(_POLITE_DELAY_SECONDS)
    return records


def _records_from_dump(dump_path: Path) -> list[dict[str, Json]]:
    parsed: Json = json.loads(dump_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        return []
    records: list[dict[str, Json]] = []
    for item in parsed:
        if isinstance(item, dict) and _is_education(item):
            record = _seed_record(item)
            if record is not None:
                records.append(record)
    return records


def _apply_extra_aliases(records: list[dict[str, Json]]) -> None:
    """Merge curated spellings ROR lacks (e.g. the bare acronym ETHZ)."""
    if not EXTRA_ALIASES_PATH.exists():
        return
    overlay: Json = json.loads(EXTRA_ALIASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(overlay, dict):
        return
    for record in records:
        extras = overlay.get(str(record["ror_id"]))
        aliases = record["aliases"]
        if isinstance(extras, list) and isinstance(aliases, list):
            aliases.extend(item for item in extras if isinstance(item, str))


def main(argv: list[str] | None = None) -> int:
    """Write the seed file from the API queries or a full ROR dump.

    Args:
        argv: CLI arguments; defaults to sys.argv.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description="Regenerate the ROR institution seed.")
    parser.add_argument("--ror-dump", type=Path, help="official ROR v2 JSON dump to process")
    args = parser.parse_args(argv)

    records = _records_from_dump(args.ror_dump) if args.ror_dump else _records_from_api()
    _apply_extra_aliases(records)
    if not records:
        sys.stderr.write("no records produced; seed left untouched\n")
        return 1
    records.sort(key=lambda record: str(record["name"]))
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    SEED_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {len(records)} records to {SEED_PATH}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
