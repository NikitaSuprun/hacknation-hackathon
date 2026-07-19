# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The only place IDs are minted.

Deterministic UUIDv5 for source-keyed entities (idempotent MERGE, fixture FKs
stable on every machine); random UUIDv4 for golden persons and event rows. The
exact input strings per entity are frozen in docs/contract.md.
"""

import uuid
from typing import Final

DEALFLOW_NS: Final[uuid.UUID] = uuid.uuid5(uuid.NAMESPACE_URL, "dealflow.hacknation.2026")


class MissingPublicationKeyError(ValueError):
    """Raised when a publication row has no natural key at all."""

    def __init__(self) -> None:
        """Fixed message; the absence itself is the whole story."""
        super().__init__("publication needs doi, arxiv_id, or openalex_id")


def _uuid5(name: str) -> str:
    return str(uuid.uuid5(DEALFLOW_NS, name))


def new_random_id() -> str:
    """Mint a UUIDv4 for golden persons and event-like rows (scores, memos, outreach)."""
    return str(uuid.uuid4())


def psr_id(source: str, source_key: str) -> str:
    """ID for silver.person_source_record: `source || ':' || source_key`."""
    return _uuid5(f"{source}:{source_key}")


def project_id(repo_id: int) -> str:
    """ID for silver.project (GitHub repo anchor): `'github_repo:' || repo_id`."""
    return _uuid5(f"github_repo:{repo_id}")


def publication_id(doi: str | None, arxiv_id: str | None, openalex_id: str | None) -> str:
    """ID for silver.publication: `coalesce(doi, 'arxiv:' || arxiv_id, openalex_id)`.

    Args:
        doi: DOI when known (highest-precedence key).
        arxiv_id: Base arXiv id without version.
        openalex_id: OpenAlex work id ('W...').

    Returns:
        The deterministic id.

    Raises:
        MissingPublicationKeyError: If every natural key is None.
    """
    if doi is not None:
        return _uuid5(doi)
    if arxiv_id is not None:
        return _uuid5(f"arxiv:{arxiv_id}")
    if openalex_id is not None:
        return _uuid5(openalex_id)
    raise MissingPublicationKeyError


def company_id(uid: str) -> str:
    """ID for silver.company: `'zefix:' || uid`."""
    return _uuid5(f"zefix:{uid}")


def venture_id(anchor_type: str, anchor_id: str) -> str:
    """ID for gold.venture: `anchor_type || ':' || anchor_id`."""
    return _uuid5(f"{anchor_type}:{anchor_id}")


def contribution_id(project: str, source_record_id: str) -> str:
    """ID for silver.contribution: `project_id || source_record_id`."""
    return _uuid5(f"{project}{source_record_id}")


def authorship_id(publication: str, source_record_id: str) -> str:
    """ID for silver.authorship: `publication_id || source_record_id`."""
    return _uuid5(f"{publication}{source_record_id}")


def officer_id(company: str, source_record_id: str, role_norm: str) -> str:
    """ID for silver.officer: `company_id || source_record_id || role_norm`."""
    return _uuid5(f"{company}{source_record_id}{role_norm}")


def link_id(person_id: str, source_record_id: str, match_method: str) -> str:
    """ID for silver.person_source_link: `person_id || source_record_id || match_method`."""
    return _uuid5(f"{person_id}{source_record_id}{match_method}")


def institution_id(canonical_name_or_ror: str) -> str:
    """ID for gold.institution_score: the ROR id when known, else the canonical name."""
    return _uuid5(canonical_name_or_ror)
