# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Raw-item validation models and intra-pipeline value objects for WS-A."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Final, Literal, final

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from contracts.models import Json


@final
class RepoRaw(BaseModel):
    """One repo bound for bronze.github_repos_raw."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["repo"]
    repo_id: int = Field(gt=0)
    full_name: str = Field(min_length=3, pattern=r".+/.+")
    payload: dict[str, Json]
    etag: str | None
    source_url: str
    scraped_at: datetime


@final
class UserRaw(BaseModel):
    """One contributor profile bound for bronze.github_users_raw."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["user"]
    user_id: int = Field(gt=0)
    login: str = Field(min_length=1)
    payload: dict[str, Json]
    source_url: str
    scraped_at: datetime


@final
class CommitRaw(BaseModel):
    """One commit bound for bronze.github_commits_raw."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["commit"]
    repo_id: int = Field(gt=0)
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    author_user_id: int | None
    payload: dict[str, Json]
    source_url: str
    scraped_at: datetime


RawItem = Annotated[RepoRaw | UserRaw | CommitRaw, Field(discriminator="kind")]

RAW_ITEM_ADAPTER: Final[TypeAdapter[RepoRaw | UserRaw | CommitRaw]] = TypeAdapter(RawItem)


@dataclass(frozen=True, slots=True)
class RepoStub:
    """A discovered repo before hydration (from REST search)."""

    node_id: str
    repo_id: int
    full_name: str
    stars: int


@dataclass(frozen=True, slots=True)
class SearchWindow:
    """One created-date slice with its search result count."""

    start: date
    end: date
    total: int


@dataclass(frozen=True, slots=True)
class ContributorStat:
    """One REST contributors entry, pre bot-filter."""

    login: str
    user_id: int
    contributions: int
    user_type: str
