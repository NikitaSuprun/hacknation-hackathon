"""Stage 4: LLM adjudication of the ambiguous Splink band (0.60-0.90).

Every verdict - including no_match - is persisted to ops.llm_adjudications so
re-runs never re-ask a settled pair. A match links at 0.90 with the verdict
JSON as evidence; unsure routes to the review queue; a schema-invalid model
response raises a typed error instead of silently passing.
"""

import json
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from contracts.interfaces import LLMClient
from contracts.models import Json, SinkRow
from er.models import PsrView, ScoredPair
from scrapers.common.jsonutil import as_mapping, get_list, get_str
from tools.ids import DEALFLOW_NS

LLM_LINK_CONFIDENCE: Final[float] = 0.90
VERDICTS: Final[frozenset[str]] = frozenset({"match", "no_match", "unsure"})
VERDICT_SCHEMA: Final[Mapping[str, Json]] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["match", "no_match", "unsure"]},
        "rationale": {"type": "string"},
        "fields_supporting": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "rationale", "fields_supporting"],
    "additionalProperties": False,
}


class VerdictSchemaError(ValueError):
    """The adjudication model returned JSON that violates the verdict schema."""

    def __init__(self, pair: str, reason: str) -> None:
        """Name the offending pair and the violation."""
        super().__init__(f"adjudication verdict for pair {pair} is invalid: {reason}")


@dataclass(frozen=True, slots=True)
class Adjudication:
    """One settled pair: the verdict plus its persistence row."""

    pair_id: str
    left: str
    right: str
    probability: float
    verdict: str
    evidence: Mapping[str, Json]
    row: SinkRow


def pair_id(a: str, b: str) -> str:
    """Deterministic id of an unordered PSR pair.

    Args:
        a: One source_record_id.
        b: The other source_record_id.

    Returns:
        UUIDv5 over the sorted pair in the dealflow namespace.
    """
    left, right = sorted((a, b))
    return str(uuid.uuid5(DEALFLOW_NS, f"adjudication:{left}|{right}"))


def _record_summary(view: PsrView) -> str:
    payload: dict[str, Json] = {
        "full_name": view.full_name,
        "name_norm": view.name_norm,
        "email_norms": list(view.email_norms),
        "orcid": view.orcid,
        "github_login": view.github_login,
        "website_url_norm": view.website_url_norm,
        "affiliation_raw": view.affiliation_raw,
        "org_norm": view.org_norm,
        "location_raw": view.location_raw,
        "country_code": view.country_code,
        "keywords": list(view.keywords),
        "source": view.source,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def build_prompt(pair: str, a: PsrView, b: PsrView) -> str:
    """Render the adjudication prompt; the first line is the scripting tag.

    Args:
        pair: The pair id.
        a: The left record view.
        b: The right record view.

    Returns:
        The full prompt text.
    """
    return (
        f"TASK:adjudicate pair={pair}\n"
        "Same real person? Answer strict JSON "
        '{"verdict":"match|no_match|unsure","rationale":"...","fields_supporting":[...]}.\n'
        f"Record A: {_record_summary(a)}\n"
        f"Record B: {_record_summary(b)}\n"
        f"Context: A is a {a.source} identity, B is a {b.source} identity."
    )


def _validated(pair: str, parsed: Mapping[str, Json] | None) -> dict[str, Json]:
    if parsed is None:
        raise VerdictSchemaError(pair, "response is not a JSON object")
    payload = dict(parsed)
    verdict = get_str(payload, "verdict")
    if verdict is None or verdict not in VERDICTS:
        raise VerdictSchemaError(
            pair, f"verdict {payload.get('verdict')!r} not in {sorted(VERDICTS)}"
        )
    if get_str(payload, "rationale") is None:
        raise VerdictSchemaError(pair, "rationale must be a string")
    fields = payload.get("fields_supporting")
    if not isinstance(fields, list) or any(not isinstance(item, str) for item in fields):
        raise VerdictSchemaError(pair, "fields_supporting must be a list of strings")
    return {
        "verdict": verdict,
        "rationale": payload["rationale"],
        "fields_supporting": get_list(payload, "fields_supporting"),
    }


def adjudicate_pairs(  # noqa: PLR0913 - the stage's full dependency surface, injected for testability
    pairs: Sequence[ScoredPair],
    views: Mapping[str, PsrView],
    llm: LLMClient,
    *,
    existing_pair_ids: frozenset[str],
    clock: Callable[[], datetime],
    pipeline_version: str,
    model: str | None = None,
) -> list[Adjudication]:
    """Ask the model about each unsettled pair in the adjudication band.

    Args:
        pairs: Splink pairs in the 0.60-0.90 band.
        views: PSR views by source_record_id.
        llm: The completion client.
        existing_pair_ids: Pairs already settled in ops.llm_adjudications.
        clock: Injected time source.
        pipeline_version: Stamped on every verdict row.
        model: Optional model override.

    Returns:
        One adjudication per newly settled pair. A model response violating
        the verdict schema surfaces as VerdictSchemaError.
    """
    results: list[Adjudication] = []
    for pair in pairs:
        settled = pair_id(pair.left, pair.right)
        if settled in existing_pair_ids:
            continue
        a = views.get(pair.left)
        b = views.get(pair.right)
        if a is None or b is None:
            continue
        response = llm.complete(build_prompt(settled, a, b), schema=VERDICT_SCHEMA, model=model)
        parsed = response.parsed if response.parsed is not None else _reparse(response.text)
        evidence = _validated(settled, parsed)
        row: SinkRow = {
            "pair_id": settled,
            "source_record_id_a": pair.left,
            "source_record_id_b": pair.right,
            "splink_probability": pair.probability,
            "verdict": str(evidence["verdict"]),
            "rationale": str(evidence["rationale"]),
            "fields_supporting": [str(f) for f in get_list(evidence, "fields_supporting")],
            "model": response.model,
            "pipeline_version": pipeline_version,
            "adjudicated_at": clock(),
        }
        results.append(
            Adjudication(
                pair_id=settled,
                left=pair.left,
                right=pair.right,
                probability=pair.probability,
                verdict=str(evidence["verdict"]),
                evidence=evidence,
                row=row,
            )
        )
    return results


def _reparse(text: str) -> Mapping[str, Json] | None:
    try:
        decoded: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    parsed = as_mapping(decoded)
    return parsed or None


def settled_pair_ids(rows: Iterable[Mapping[str, Json]]) -> frozenset[str]:
    """Pair ids already present in ops.llm_adjudications.

    Args:
        rows: Existing adjudication rows.

    Returns:
        The settled pair-id set.
    """
    return frozenset(str(row.get("pair_id")) for row in rows)
