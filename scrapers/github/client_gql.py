# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Alias-batched GraphQL: repo hydration (25/query) and profiles (50/query).

Per-alias error policy: NOT_FOUND (deleted/renamed between search and hydrate)
is logged and dropped; any other per-alias error is retried once in a batch of
one, then surfaced as a failure the scraper turns into a bronze._rejects row.
Every query carries a rateLimit tail for live headroom logging.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from structlog.typing import FilteringBoundLogger

from contracts.models import Json
from scrapers.common.http import HttpClient
from scrapers.common.jsonutil import as_list, as_mapping, get_list, get_map, get_str
from scrapers.github.models import RepoStub

GQL_URL: Final[str] = "https://api.github.com/graphql"
GQL_BUCKET: Final[str] = "graphql"
HYDRATE_BATCH_SIZE: Final[int] = 25
PROFILE_BATCH_SIZE: Final[int] = 50
NOT_FOUND: Final[str] = "NOT_FOUND"
RATE_LIMIT_TAIL: Final[str] = "rateLimit { cost remaining resetAt }"

# __SINCE__ becomes ', since: "<ISO>"' on incremental runs (empty on backfill).
REPO_FRAGMENT: Final[str] = """
fragment RepoFields on Repository {
  databaseId
  nameWithOwner
  description
  createdAt
  pushedAt
  stargazerCount
  forkCount
  isFork
  homepageUrl
  licenseInfo { spdxId }
  repositoryTopics(first: 20) { nodes { topic { name } } }
  languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
  fundingLinks { platform url }
  owner {
    __typename
    login
    ... on Organization { isVerified websiteUrl email membersWithRole { totalCount } }
    ... on User { databaseId }
  }
  defaultBranchRef {
    target {
      ... on Commit {
        history(first: 100__SINCE__) {
          totalCount
          nodes {
            oid
            additions
            deletions
            committedDate
            messageHeadline
            author { name email date user { login databaseId } }
          }
        }
      }
    }
  }
}
"""

USER_FRAGMENT: Final[str] = """
fragment UserFields on User {
  databaseId
  login
  name
  company
  location
  websiteUrl
  email
  bio
  twitterUsername
  avatarUrl
  followers { totalCount }
  organizations(first: 10) { nodes { login name } }
  socialAccounts(first: 10) { nodes { provider url } }
}
"""


@dataclass(frozen=True, slots=True)
class GqlFailure:
    """One alias that stayed broken after the individual retry."""

    key: str
    message: str


def repo_query(full_names: Sequence[str], since: str | None) -> str:
    """Build the alias-batched hydration query.

    Args:
        full_names: 'owner/repo' names, one alias each.
        since: ISO GitTimestamp bounding commit history, or None on backfill.

    Returns:
        The GraphQL document.
    """
    since_clause = f", since: {json.dumps(since)}" if since is not None else ""
    aliases: list[str] = []
    for index, full_name in enumerate(full_names):
        owner, _, name = full_name.partition("/")
        aliases.append(
            f"n{index}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) "
            "{ ...RepoFields }"
        )
    body = "\n  ".join([RATE_LIMIT_TAIL, *aliases])
    fragment = REPO_FRAGMENT.replace("__SINCE__", since_clause)
    return f"query Hydrate {{\n  {body}\n}}\n{fragment}"


def user_query(logins: Sequence[str]) -> str:
    """Build the alias-batched profile query.

    Args:
        logins: Contributor logins, one alias each.

    Returns:
        The GraphQL document.
    """
    aliases = [
        f"n{index}: user(login: {json.dumps(login)}) {{ ...UserFields }}"
        for index, login in enumerate(logins)
    ]
    body = "\n  ".join([RATE_LIMIT_TAIL, *aliases])
    return f"query Profiles {{\n  {body}\n}}\n{USER_FRAGMENT}"


QueryBuilder = Callable[[Sequence[str]], str]


class GithubGraphql:
    """Batched GraphQL execution with the per-alias error policy."""

    def __init__(self, http: HttpClient, log: FilteringBoundLogger) -> None:
        """Ride the shared HttpClient (bucket 'graphql')."""
        self._http: Final[HttpClient] = http
        self._log: Final[FilteringBoundLogger] = log

    def hydrate_repos(
        self, stubs: Sequence[RepoStub], since: str | None
    ) -> tuple[dict[str, dict[str, Json]], list[GqlFailure]]:
        """Hydrate up to 25 repos in one query.

        Args:
            stubs: The discovered repos (one batch).
            since: ISO GitTimestamp bounding commit history, or None.

        Returns:
            Repo objects keyed by full_name, plus persistent failures.
        """
        names = [stub.full_name for stub in stubs]
        return self._with_retry(names, lambda keys: repo_query(keys, since))

    def user_profiles(
        self, logins: Sequence[str]
    ) -> tuple[dict[str, dict[str, Json]], list[GqlFailure]]:
        """Fetch up to 50 profiles in one query.

        Args:
            logins: Contributor logins (one batch).

        Returns:
            Profile objects keyed by login, plus persistent failures.
        """
        return self._with_retry(list(logins), user_query)

    def _execute(self, query: str) -> tuple[dict[str, Json], dict[str, tuple[str, str]]]:
        response = self._http.post_json(GQL_URL, {"query": query}, bucket=GQL_BUCKET)
        body = as_mapping(response.json())
        data = get_map(body, "data")
        errors: dict[str, tuple[str, str]] = {}
        for entry in as_list(body.get("errors")):
            error = as_mapping(entry)
            path = get_list(error, "path")
            alias = path[0] if path and isinstance(path[0], str) else ""
            errors[alias] = (
                get_str(error, "type") or "UNKNOWN",
                get_str(error, "message") or "unspecified GraphQL error",
            )
        self._note_rate(data)
        return data, errors

    def _note_rate(self, data: dict[str, Json]) -> None:
        rate = get_map(data, "rateLimit")
        if rate:
            self._log.info("graphql rate", cost=rate.get("cost"), remaining=rate.get("remaining"))

    def _query_map(
        self, keys: Sequence[str], build: QueryBuilder
    ) -> tuple[dict[str, dict[str, Json]], dict[str, str]]:
        data, errors = self._execute(build(keys))
        results: dict[str, dict[str, Json]] = {}
        retryable: dict[str, str] = {}
        for index, key in enumerate(keys):
            alias = f"n{index}"
            obj = get_map(data, alias)
            if obj:
                results[key] = obj
                continue
            error_type, message = errors.get(alias, ("UNKNOWN", "null result without error"))
            if error_type == NOT_FOUND:
                self._log.info("graphql not found", key=key)
            else:
                retryable[key] = message
        return results, retryable

    def _with_retry(
        self, keys: Sequence[str], build: QueryBuilder
    ) -> tuple[dict[str, dict[str, Json]], list[GqlFailure]]:
        results, retryable = self._query_map(keys, build)
        failures: list[GqlFailure] = []
        for key, message in retryable.items():
            retry_results, retry_bad = self._query_map([key], build)
            if key in retry_results:
                results[key] = retry_results[key]
            else:
                failures.append(GqlFailure(key=key, message=retry_bad.get(key, message)))
        return results, failures
