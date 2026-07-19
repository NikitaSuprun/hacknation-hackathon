# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""The unified PublicationRecord family (source-agnostic core + source extras).

Affiliation caveat (contract): an author's affiliation string is a
submission-time snapshot and role-blind (student and professor look alike);
ORCID coverage is a minority in CS. Author-to-person links derived from these
records are candidate links with confidence, confirmed by a second signal or
the interview — never presented as current employment facts in memos.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Final, Literal, final

from pydantic import BaseModel, ConfigDict, Field

from contracts.models import Json

SCHEMA_VERSION: Final[int] = 1

DataSource = Literal["arxiv", "openalex", "s2"]
CodeHost = Literal["github", "gitlab", "huggingface"]


@final
class CodeLink(BaseModel):
    """One extracted paper-to-code pointer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    host: CodeHost
    owner: str
    repo: str


@final
class PublicationUrls(BaseModel):
    """Landing and PDF locations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    landing: str
    pdf: str | None


@final
class PublicationAuthor(BaseModel):
    """One author position; affiliations are submission-time snapshots."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    position: int = Field(gt=0)
    full_name: str = Field(min_length=1)
    orcid: str | None
    source_author_id: str | None
    affiliation_strings: tuple[str, ...]
    is_corresponding: bool | None


@final
class PublicationRecord(BaseModel):
    """The unified cross-source publication shape (see interfaces.md)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    publication_uid: str
    data_source: DataSource
    source_native_id: str = Field(min_length=1)
    doi: str | None
    title: str = Field(min_length=1)
    abstract: str | None
    published_at: date | None
    venue: str | None
    categories: tuple[str, ...]
    urls: PublicationUrls
    code_links: tuple[CodeLink, ...]
    authors: tuple[PublicationAuthor, ...]
    citation_count: int | None
    citation_count_source: str | None
    citation_count_as_of: date | None
    retrieved_at: datetime
    schema_version: int
    source_extras: dict[str, Json]


@dataclass(frozen=True, slots=True)
class PendingPaper:
    """One arXiv paper awaiting enrichment (DOI known when published)."""

    arxiv_id: str
    doi: str | None
