"""The real Stage-A category scorers (1.1.1 / 1.1.2 / 1.1.4 / 2.2 / ideal-match).

Rubrics per docs/plan/reference/scoring-and-memo.md. The fixture golden path
runs scripted verdicts instead; these implementations carry the true formulas
and are unit-tested directly, with documented divergences from the seeded
fixture values (e.g. schools computes 97 where the fixture pins 92).
"""

from collections.abc import Mapping, Sequence
from typing import Final

from contracts.interfaces import CategoryScorer, LLMClient
from contracts.models import CategoryScore, Evidence, FeatureBundle, Json, VentureView
from scoring.categories.base import VENTURE_MAX_WEIGHT, VENTURE_MEAN_WEIGHT
from scoring.profile_text import domain_fit
from scoring.snapshot import get_float
from scrapers.common.jsonutil import as_mapping, get_list, get_map, get_str

SCHOOLS_MAX_WEIGHT: Final[float] = 0.7
SCHOOLS_MEAN_WEIGHT: Final[float] = 0.3

COLLAB_STRONG_SCORE: Final[float] = 90.0
COLLAB_SINGLE_SCORE: Final[float] = 65.0
COLLAB_CURRENT_ONLY_SCORE: Final[float] = 30.0
COLLAB_STRONG_CONTEXTS: Final[int] = 2
COLLAB_STRONG_YEARS: Final[float] = 2.0
COLLAB_MIN_TEAM: Final[int] = 2

EXPERIENCE_SUBWEIGHTS: Final[tuple[tuple[str, float], ...]] = (
    ("top_company", 0.25),
    ("github", 0.30),
    ("zero_to_one", 0.20),
    ("papers", 0.15),
    ("fit", 0.10),
)

DOMAIN_FIT_WEIGHT: Final[float] = 1.0
STARS_WEIGHTED_SCALE: Final[float] = 10.0

_DEFENSIBILITY_SCHEMA: Final[dict[str, Json]] = {
    "type": "object",
    "required": ["score", "rationale"],
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 100},
        "rationale": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["claim", "source_url"],
                "properties": {
                    "claim": {"type": "string"},
                    "source_url": {"type": "string"},
                    "source_type": {"type": ["string", "null"]},
                },
            },
        },
    },
}


def percentile(value: float, population: Sequence[float]) -> float:
    """Fraction of the population at or below the value.

    Args:
        value: The candidate value.
        population: All observed values (the candidate included).

    Returns:
        0..1 percentile; 1.0 for an empty population.
    """
    if not population:
        return 1.0
    return sum(1 for other in population if other <= value) / len(population)


def _aggregate(person_scores: Sequence[float]) -> float:
    mean = sum(person_scores) / len(person_scores)
    return round(VENTURE_MEAN_WEIGHT * mean + VENTURE_MAX_WEIGHT * max(person_scores), 1)


def _features_evidence(claim: str, source_url: str) -> tuple[Evidence, ...]:
    return (
        Evidence(
            claim=claim, source_url=source_url, source_type="features", snippet=None, weight=None
        ),
    )


def _venture_url(venture: VentureView) -> str:
    url = get_str(dict(venture.extras), "source_url") or get_str(
        dict(venture.extras), "website_url"
    )
    return url or f"venture:{venture.venture_id}"


class IndividualExperienceScorer:
    """1.1.1: percentile-normalized subweights over the shared feature layer."""

    category: str = "individual_experience"

    def __init__(self, population: Mapping[str, Mapping[str, float]]) -> None:
        """Bind the population features for percentile normalization."""
        self._population: Final[Mapping[str, Mapping[str, float]]] = population

    def _population_values(self, key: str) -> list[float]:
        return [
            value
            for features in self._population.values()
            if (value := features.get(key)) is not None
        ]

    def _github_component(self, features: Mapping[str, float]) -> float | None:
        parts: list[float] = []
        for key in ("stars_weighted", "commits_12mo"):
            value = features.get(key)
            if value is not None:
                parts.append(percentile(value, self._population_values(key)))
        quality = features.get("commit_quality")
        if quality is not None:
            parts.append(quality / 100.0)
        return sum(parts) / len(parts) if parts else None

    def _subscores(self, features: Mapping[str, float]) -> dict[str, float]:
        candidates: dict[str, float | None] = {
            "top_company": features.get("top_co_flag"),
            "github": self._github_component(features),
            "zero_to_one": features.get("zero_to_one_flag"),
            "papers": (
                percentile(value, self._population_values("citations_total"))
                if (value := features.get("citations_total")) is not None
                else None
            ),
            "fit": (
                fit / 100.0 if (fit := features.get("experience_problem_fit")) is not None else None
            ),
        }
        return {key: value for key, value in candidates.items() if value is not None}

    def _person_score(self, features: Mapping[str, float]) -> float | None:
        subscores = self._subscores(features)
        weights = [(key, weight) for key, weight in EXPERIENCE_SUBWEIGHTS if key in subscores]
        total = sum(weight for _, weight in weights)
        if total <= 0.0:
            return None
        return 100.0 * sum(subscores[key] * weight for key, weight in weights) / total

    def score(self, venture: VentureView, features: FeatureBundle) -> CategoryScore:
        """Score the venture's team experience.

        Args:
            venture: The venture snapshot.
            features: The shared feature layer.

        Returns:
            The category verdict (score None without any member features).
        """
        person_scores = [
            score
            for person_id in venture.member_person_ids
            if (member := features.person_features.get(person_id)) is not None
            and (score := self._person_score(member)) is not None
        ]
        if not person_scores:
            return CategoryScore(
                category=self.category,
                score=None,
                confidence=0.2,
                method="sql_features",
                rationale="no member features available",
                evidence=(),
            )
        value = _aggregate(person_scores)
        claim = f"{len(person_scores)} member(s) scored from the shared feature layer"
        return CategoryScore(
            category=self.category,
            score=value,
            confidence=0.8,
            method="sql_features",
            rationale=claim,
            evidence=_features_evidence(claim, _venture_url(venture)),
        )


class SchoolsScorer:
    """1.1.2: deterministic lookup — 0.7 x max tier + 0.3 x mean of known tiers."""

    category: str = "schools"

    def score(self, venture: VentureView, features: FeatureBundle) -> CategoryScore:
        """Score the team's calibrated school tiers.

        Args:
            venture: The venture snapshot.
            features: The shared feature layer (school_tier on 0..1).

        Returns:
            The category verdict (score None when no tier is known).
        """
        tiers = [
            tier * 100.0
            for person_id in venture.member_person_ids
            if (member := features.person_features.get(person_id)) is not None
            and (tier := member.get("school_tier")) is not None
        ]
        if not tiers:
            return CategoryScore(
                category=self.category,
                score=None,
                confidence=0.2,
                method="deterministic",
                rationale="no known school tiers among members",
                evidence=(),
            )
        value = round(
            SCHOOLS_MAX_WEIGHT * max(tiers) + SCHOOLS_MEAN_WEIGHT * (sum(tiers) / len(tiers)), 1
        )
        claim = f"max tier {max(tiers):.0f} across {len(tiers)} known member(s)"
        return CategoryScore(
            category=self.category,
            score=value,
            confidence=0.8,
            method="deterministic",
            rationale=claim,
            evidence=_features_evidence(claim, _venture_url(venture)),
        )


class PriorCollaborationScorer:
    """1.1.4: shared history — >=2 contexts or >=2 years 90; one 65; current-only 30."""

    category: str = "prior_collaboration"

    def _verdict(self, contexts: int, years: float) -> tuple[float, str]:
        if contexts >= COLLAB_STRONG_CONTEXTS or years >= COLLAB_STRONG_YEARS:
            return COLLAB_STRONG_SCORE, (f"{contexts} shared contexts spanning {years:.1f} years")
        if contexts == 1:
            return COLLAB_SINGLE_SCORE, "one shared context before this venture"
        return COLLAB_CURRENT_ONLY_SCORE, "no shared history beyond the current venture"

    def score(self, venture: VentureView, features: FeatureBundle) -> CategoryScore:
        """Score prior collaboration from the assembled overlap extras.

        Args:
            venture: The venture snapshot; extras carry collab_contexts /
                collab_years assembled from the silver snapshot.
            features: Unused (protocol shape).

        Returns:
            The category verdict (score None for a solo team).
        """
        del features
        extras = dict(venture.extras)
        if len(venture.member_person_ids) < COLLAB_MIN_TEAM:
            return CategoryScore(
                category=self.category,
                score=None,
                confidence=0.5,
                method="sql_overlap",
                rationale="solo team: category not applicable",
                evidence=(),
            )
        contexts = int(get_float(extras, "collab_contexts") or 0.0)
        years = get_float(extras, "collab_years") or 0.0
        value, claim = self._verdict(contexts, years)
        return CategoryScore(
            category=self.category,
            score=value,
            confidence=0.8,
            method="sql_overlap",
            rationale=claim,
            evidence=_features_evidence(claim, _venture_url(venture)),
        )


def _parsed_evidence(parsed: Mapping[str, Json], fallback_url: str) -> tuple[Evidence, ...]:
    items: list[Evidence] = []
    for entry in get_list(dict(parsed), "evidence"):
        mapping = as_mapping(entry)
        claim = get_str(mapping, "claim")
        if claim is None:
            continue
        items.append(
            Evidence(
                claim=claim,
                source_url=get_str(mapping, "source_url") or fallback_url,
                source_type=get_str(mapping, "source_type"),
                snippet=get_str(mapping, "snippet"),
                weight=None,
            )
        )
    return tuple(items)


class ProductDefensibilityScorer:
    """2.2: batch ai_query over README/deps/velocity — no web access."""

    category: str = "product_defensibility"

    def __init__(self, llm: LLMClient) -> None:
        """Bind the LLM seam."""
        self._llm: Final[LLMClient] = llm

    def score(self, venture: VentureView, features: FeatureBundle) -> CategoryScore:
        """Score defensibility via a schema-constrained completion.

        Args:
            venture: The venture snapshot; extras carry description/license/stars.
            features: Unused (protocol shape).

        Returns:
            The category verdict with the model's evidence passed through.
        """
        del features
        extras = dict(venture.extras)
        context = {
            "name": venture.name,
            "one_liner": venture.one_liner,
            "description": get_str(extras, "description"),
            "license": get_str(extras, "license"),
            "stars": get_float(extras, "stars"),
        }
        prompt = (
            f"TASK:product_defensibility venture={venture.venture_id}\n"
            "Score 0-100: own-model/hard-tech high, thin wrapper low.\n"
            f"{context}"
        )
        response = self._llm.complete(prompt, schema=_DEFENSIBILITY_SCHEMA)
        parsed = response.parsed or {}
        value = get_float(dict(parsed), "score")
        return CategoryScore(
            category=self.category,
            score=value,
            confidence=get_float(dict(parsed), "confidence") or 0.5,
            method="ai_query",
            rationale=get_str(dict(parsed), "rationale"),
            evidence=_parsed_evidence(parsed, _venture_url(venture)),
        )


class IdealMatchScorer:
    """Structured ideal-candidate match: directional closeness plus domain fit."""

    category: str = "ideal_match"

    def __init__(
        self,
        profile_json: Mapping[str, Json],
        ideal_embedding: Sequence[float],
        person_embeddings: Mapping[str, Sequence[float]],
    ) -> None:
        """Bind the ideal profile, its embedding, and member embeddings."""
        self._profile: Final[Mapping[str, Json]] = profile_json
        self._ideal_embedding: Final[Sequence[float]] = ideal_embedding
        self._person_embeddings: Final[Mapping[str, Sequence[float]]] = person_embeddings

    @staticmethod
    def _normalized(key: str, value: float) -> float:
        if key == "stars_weighted":
            return min(1.0, value / STARS_WEIGHTED_SCALE)
        return min(1.0, value)

    def _closeness(self, features: Mapping[str, float]) -> tuple[float, float]:
        numeric = get_map(dict(self._profile), "numeric_features")
        weights = get_map(dict(self._profile), "feature_weights")
        score = 0.0
        total = 0.0
        for key, target in numeric.items():
            if isinstance(target, bool) or not isinstance(target, int | float) or target <= 0:
                continue
            candidate = features.get(key)
            if candidate is None:
                continue
            weight = get_float(weights, key)
            weight = 1.0 if weight is None else weight
            observed = self._normalized(key, candidate)
            score += weight * min(1.0, observed / float(target))
            total += weight
        return score, total

    def _person_match(self, person_id: str, features: Mapping[str, float]) -> float | None:
        score, total = self._closeness(features)
        embedding = self._person_embeddings.get(person_id)
        if embedding is not None:
            fit = max(0.0, domain_fit(embedding, self._ideal_embedding))
            score += DOMAIN_FIT_WEIGHT * fit
            total += DOMAIN_FIT_WEIGHT
        if total <= 0.0:
            return None
        return 100.0 * score / total

    def score(self, venture: VentureView, features: FeatureBundle) -> CategoryScore:
        """Score the venture against the structured ideal profile.

        Args:
            venture: The venture snapshot.
            features: The shared feature layer.

        Returns:
            The category verdict (score None without matchable members).
        """
        matches = [
            match
            for person_id in venture.member_person_ids
            if (member := features.person_features.get(person_id)) is not None
            and (match := self._person_match(person_id, member)) is not None
        ]
        if not matches:
            return CategoryScore(
                category=self.category,
                score=None,
                confidence=0.2,
                method="structured_match",
                rationale="no matchable member features",
                evidence=(),
            )
        value = _aggregate(matches)
        claim = f"directional feature match over {len(matches)} member(s)"
        return CategoryScore(
            category=self.category,
            score=value,
            confidence=0.8,
            method="structured_match",
            rationale=claim,
            evidence=_features_evidence(claim, _venture_url(venture)),
        )


def stage_a_registry(
    llm: LLMClient,
    population: Mapping[str, Mapping[str, float]],
    profile_json: Mapping[str, Json],
    ideal_embedding: Sequence[float],
    person_embeddings: Mapping[str, Sequence[float]],
) -> dict[str, CategoryScorer]:
    """The default Stage-A registry over the real scorers.

    Args:
        llm: The LLM seam for 2.2.
        population: Population features for percentile normalization.
        profile_json: The active ideal-candidate profile payload.
        ideal_embedding: The ideal profile's unit embedding.
        person_embeddings: Member profile embeddings keyed by person id.

    Returns:
        Scorers for the five Stage-A categories.
    """
    return {
        "individual_experience": IndividualExperienceScorer(population),
        "schools": SchoolsScorer(),
        "prior_collaboration": PriorCollaborationScorer(),
        "product_defensibility": ProductDefensibilityScorer(llm),
        "ideal_match": IdealMatchScorer(profile_json, ideal_embedding, person_embeddings),
    }
