"""The funding backbone: has this founder/company already raised?

Cascade order per scoring-and-memo.md: SOGC capital-increase filings (the
free realtime proxy for a priced Swiss round), then the static funded list,
then not-funded. `classify_funding_signal` turns the verdict plus funding
vocabulary in project/company text into the tri-state candidate-pool signal,
with a Haiku confirmation for ambiguous vocabulary hits.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from contracts.interfaces import LLMClient
from contracts.models import CompanyRef, Evidence, FundingStatus, Json, PersonRef
from scoring.snapshot import Row, get_bool
from scrapers.common.jsonutil import get_map, get_str
from tools.norm import org_key

CAPITAL_INCREASE_RUBRICS: Final[frozenset[str]] = frozenset({"HR02"})
CAPITAL_INCREASE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"kapitalerh(?:ö|oe?)hung|augmentation du capital", re.IGNORECASE
)
FUNDING_VOCAB_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bseed\b|\bseries [a-c]\b|\braised\b|\bbacked by\b|\binvestors\b", re.IGNORECASE
)
# org_key'd names of companies known to have raised (fixture-scale stand-in
# for the Startupticker / Crunchbase snapshot cascade stages).
STATIC_FUNDED_COMPANIES: Final[frozenset[str]] = frozenset({"keller advisory"})

SIGNAL_NONE: Final[str] = "none_found"
SIGNAL_SUSPECTED: Final[str] = "suspected"
SIGNAL_CONFIRMED: Final[str] = "confirmed_funded"
_SIGNALS: Final[frozenset[str]] = frozenset({SIGNAL_NONE, SIGNAL_SUSPECTED, SIGNAL_CONFIRMED})

_CONFIRM_SCHEMA: Final[dict[str, Json]] = {
    "type": "object",
    "required": ["verdict"],
    "properties": {
        "verdict": {"enum": [SIGNAL_NONE, SIGNAL_SUSPECTED, SIGNAL_CONFIRMED]},
        "rationale": {"type": "string"},
    },
}

NOT_FUNDED: Final[FundingStatus] = FundingStatus(
    funded=False, stage=None, amount_chf=None, as_of=None, source=None
)


@dataclass(frozen=True, slots=True)
class FundingProbe:
    """Everything the tri-state pool signal needs for one venture."""

    venture_id: str
    company: CompanyRef | None
    texts: tuple[str, ...]
    source_url: str


class StaticCascadeFundedFounderResolver:
    """FundedFounderResolver over SOGC filings and the static funded list."""

    def __init__(
        self, sogc_rows: Sequence[Row], officers: Sequence[Row], companies: Sequence[Row]
    ) -> None:
        """Index filings by company uid and officers by person."""
        self._sogc_by_uid: Final[dict[str, list[Row]]] = {}
        for row in sogc_rows:
            uid = get_str(dict(row), "uid")
            if uid is not None:
                self._sogc_by_uid.setdefault(uid, []).append(row)
        self._companies_by_id: Final[dict[str, Row]] = {}
        for company in companies:
            company_id = get_str(dict(company), "company_id")
            if company_id is not None:
                self._companies_by_id[company_id] = company
        self._company_ids_by_person: Final[dict[str, list[str]]] = {}
        for officer in officers:
            person_id = get_str(dict(officer), "person_id")
            company_id = get_str(dict(officer), "company_id")
            if person_id is not None and company_id is not None:
                self._company_ids_by_person.setdefault(person_id, []).append(company_id)

    def _capital_increase(self, uid: str) -> FundingStatus | None:
        for filing in self._sogc_by_uid.get(uid, []):
            row = dict(filing)
            rubric = get_str(row, "sub_rubric")
            text = get_str(get_map(row, "payload"), "publicationText") or ""
            if rubric in CAPITAL_INCREASE_RUBRICS or CAPITAL_INCREASE_PATTERN.search(text):
                published = get_str(row, "published_date")
                return FundingStatus(
                    funded=True,
                    stage="priced_round",
                    amount_chf=None,
                    as_of=date.fromisoformat(published) if published else None,
                    source="sogc_capital_increase",
                )
        return None

    def _company_status(self, ref: CompanyRef) -> FundingStatus:
        if ref.uid is not None:
            filed = self._capital_increase(ref.uid)
            if filed is not None:
                return filed
        if org_key(ref.name) in STATIC_FUNDED_COMPANIES:
            return FundingStatus(
                funded=True, stage=None, amount_chf=None, as_of=None, source="static_list"
            )
        return NOT_FUNDED

    def _person_status(self, ref: PersonRef) -> FundingStatus:
        for company_id in self._company_ids_by_person.get(ref.person_id, []):
            company = self._companies_by_id.get(company_id)
            if company is None:
                continue
            row = dict(company)
            name = get_str(row, "name")
            if name is None:
                continue
            status = self._company_status(
                CompanyRef(company_id=company_id, uid=get_str(row, "uid"), name=name)
            )
            if status.funded:
                return status
        return NOT_FUNDED

    def resolve(self, ref: PersonRef | CompanyRef) -> FundingStatus:
        """Cascade through the funding sources and return the best verdict.

        Args:
            ref: The person or company to check.

        Returns:
            The funding verdict; `funded=False` when nothing matched.
        """
        if isinstance(ref, CompanyRef):
            return self._company_status(ref)
        return self._person_status(ref)


def _vocabulary_hit(texts: tuple[str, ...]) -> str | None:
    for text in texts:
        match = FUNDING_VOCAB_PATTERN.search(text)
        if match is not None:
            return match.group(0)
    return None


def _confirm_with_llm(probe: FundingProbe, hit: str, llm: LLMClient) -> str:
    prompt = (
        f"TASK:funding_confirm venture={probe.venture_id}\n"
        f"Vocabulary hit: {hit!r}\n"
        "Does this text describe the venture itself having raised institutional "
        "funding (confirmed_funded), an ambiguous mention (suspected), or "
        "unrelated usage (none_found)?\n" + "\n".join(probe.texts)
    )
    response = llm.complete(prompt, schema=_CONFIRM_SCHEMA)
    verdict = get_str(dict(response.parsed), "verdict") if response.parsed else None
    return verdict if verdict in _SIGNALS else SIGNAL_SUSPECTED


def classify_funding_signal(
    probe: FundingProbe,
    resolver: StaticCascadeFundedFounderResolver,
    llm: LLMClient,
) -> tuple[str, list[Evidence]]:
    """Compute the tri-state candidate-pool funding signal for one venture.

    Args:
        probe: The venture's company link and searchable text.
        resolver: The funded-founder cascade.
        llm: Haiku confirmation for ambiguous vocabulary hits.

    Returns:
        The signal ('none_found' | 'suspected' | 'confirmed_funded') plus
        the evidence supporting it (empty for a clean none_found).
    """
    if probe.company is not None:
        status = resolver.resolve(probe.company)
        if status.funded:
            claim = f"{probe.company.name} shows a prior raise via {status.source}"
            evidence = Evidence(
                claim=claim,
                source_url=probe.source_url,
                source_type=status.source,
                snippet=None,
                weight=None,
            )
            return SIGNAL_CONFIRMED, [evidence]
    hit = _vocabulary_hit(probe.texts)
    if hit is not None:
        verdict = _confirm_with_llm(probe, hit, llm)
        evidence = Evidence(
            claim=f"funding vocabulary {hit!r} found in venture text",
            source_url=probe.source_url,
            source_type="text_heuristic",
            snippet=hit,
            weight=None,
        )
        return verdict, [evidence]
    return SIGNAL_NONE, []


def interview_funding_signal(extracted: Row) -> str | None:
    """Map a consented interview's funding answer onto the pool signal.

    Args:
        extracted: The interview's extracted payload.

    Returns:
        'confirmed_funded' / 'none_found', or None when unanswered.
    """
    funding = get_map(dict(extracted), "funding_status")
    raised = get_bool(funding, "raised_before")
    if raised is None:
        return None
    return SIGNAL_CONFIRMED if raised else SIGNAL_NONE
