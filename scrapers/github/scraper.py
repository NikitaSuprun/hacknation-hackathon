"""The GitHub scraper: discovery, hydration, contributors, profiles.

ETags live in the cursor VARIANT (pruned to the current window each run) and
are mirrored to bronze.github_repos_raw.etag. On a README 304 the fresh
GraphQL payload is recomposed with the stored README via the readback seam;
a missing readback row falls back to an unconditional refetch (self-healing).
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final, Protocol

from structlog.typing import FilteringBoundLogger

from contracts.models import BronzeRecord, Cursor, Json, RawBatch, RunResult
from scrapers.common.base import execute_run
from scrapers.common.jsonutil import as_list, as_mapping, get_int, get_list, get_map, get_str
from scrapers.common.sink import build_deps
from scrapers.common.state import SqlRunner, require_identifier
from scrapers.github.client_gql import (
    HYDRATE_BATCH_SIZE,
    PROFILE_BATCH_SIZE,
    GithubGraphql,
    GqlFailure,
)
from scrapers.github.client_rest import GithubRest
from scrapers.github.contributors import core_contributors
from scrapers.github.discovery import discover
from scrapers.github.models import ContributorStat, RepoStub
from scrapers.github.normalize import ERROR_KIND, SOURCE, normalize_batch
from scrapers.github.signals import funded_signals

README_MAX_BYTES: Final[int] = 200_000
COMMIT_OVERLAP_DAYS: Final[int] = 1
NOREPLY_SUFFIX: Final[str] = "users.noreply.github.com"
NOT_MODIFIED: Final[int] = 304
NOT_FOUND_STATUS: Final[int] = 404


class ReadbackReader(Protocol):
    """Batched bronze read-back of stored READMEs (for 304 recomposition)."""

    def readmes(self, repo_ids: Sequence[int]) -> dict[int, str]:
        """Return stored readme_md text per repo id (missing rows omitted)."""
        ...


class NullReadback:
    """No read-back (dry runs); every 304 self-heals via a refetch."""

    def readmes(self, repo_ids: Sequence[int]) -> dict[int, str]:
        """Return nothing.

        Args:
            repo_ids: Ignored.

        Returns:
            An empty mapping.
        """
        del repo_ids
        return {}


class WarehouseReadback:
    """One batched SELECT of stored READMEs for the repos with known ETags."""

    def __init__(self, runner: SqlRunner, catalog: str) -> None:
        """Bind to one catalog."""
        self._runner: Final[SqlRunner] = runner
        self._catalog: Final[str] = require_identifier(catalog)

    def readmes(self, repo_ids: Sequence[int]) -> dict[int, str]:
        """Read stored readme_md for the given repos.

        Args:
            repo_ids: Repo ids with a stored ETag.

        Returns:
            readme_md text per repo id; repos without one are omitted.
        """
        if not repo_ids:
            return {}
        id_list = ", ".join(str(int(repo_id)) for repo_id in repo_ids)
        rows = self._runner.execute(
            "SELECT repo_id, CAST(payload:readme_md AS STRING) "
            f"FROM {self._catalog}.bronze.github_repos_raw WHERE repo_id IN ({id_list})"
        )
        found: dict[int, str] = {}
        for row in rows:
            if isinstance(row[0], int) and isinstance(row[1], str):
                found[row[0]] = row[1]
        return found


@dataclass(frozen=True, slots=True)
class GithubDeps:
    """Everything the scraper composes over; injected for deterministic tests."""

    rest: GithubRest
    gql: GithubGraphql
    readback: ReadbackReader
    since: date
    limit: int
    clock: Callable[[], datetime]
    run_id: str
    log: FilteringBoundLogger
    explicit_repos: tuple[str, ...]


def _chunks[T](items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _error_item(failure: GqlFailure) -> dict[str, Json]:
    return {
        "kind": ERROR_KIND,
        "natural_key": failure.key,
        "error": failure.message,
        "raw": {"key": failure.key},
    }


class GithubScraper:
    """BaseScraper implementation for the GitHub source."""

    source: str = SOURCE

    def __init__(self, deps: GithubDeps) -> None:
        """Start with empty per-run accumulators."""
        self._deps: Final[GithubDeps] = deps
        self._new_readme_etags: Final[dict[str, str]] = {}
        self._new_contrib_etags: Final[dict[str, str]] = {}
        self._core_logins: Final[set[str]] = set()
        self._emails: Final[dict[str, list[dict[str, Json]]]] = {}
        self._window_end: date = deps.since

    def fetch(self, cursor: Cursor) -> Iterator[RawBatch]:
        """Discover, hydrate, and profile; yields kind-tagged raw batches.

        Args:
            cursor: The stored cursor (ETags, commit watermark).

        Yields:
            Batches of repo/commit items, then user-profile batches.
        """
        state = dict(cursor.state)
        readme_etags = _str_map(state.get("readme_etags"))
        contrib_etags = _str_map(state.get("contrib_etags"))
        watermark = state.get("commits_since")
        commits_since = watermark if isinstance(watermark, str) else None
        self._window_end = self._deps.clock().date()
        if self._deps.explicit_repos:
            stubs = self._lookup_stubs(self._deps.explicit_repos)
        else:
            stubs = discover(
                self._deps.rest,
                self._deps.since,
                self._window_end,
                self._deps.limit,
                self._deps.log,
            )
        cached = self._deps.readback.readmes(
            [stub.repo_id for stub in stubs if str(stub.repo_id) in readme_etags]
        )
        for chunk in _chunks(stubs, HYDRATE_BATCH_SIZE):
            yield self._hydrate_batch(chunk, commits_since, readme_etags, contrib_etags, cached)
        for logins in _chunks(sorted(self._core_logins), PROFILE_BATCH_SIZE):
            yield self._profile_batch(logins)

    def normalize(self, raw: RawBatch) -> list[BronzeRecord]:
        """Validate one raw batch into bronze records.

        Args:
            raw: The fetched batch.

        Returns:
            Bronze records (rejects included).
        """
        return normalize_batch(raw, self._deps.run_id, self._deps.clock())

    def next_cursor(self) -> Cursor:
        """Render the cursor for the next incremental run.

        Returns:
            Window end, commit watermark (1-day overlap), and pruned ETags.
        """
        overlap_start = self._window_end - timedelta(days=COMMIT_OVERLAP_DAYS)
        return Cursor(
            source=SOURCE,
            state={
                "window_end": self._window_end.isoformat(),
                "commits_since": f"{overlap_start.isoformat()}T00:00:00Z",
                "readme_etags": dict(self._new_readme_etags),
                "contrib_etags": dict(self._new_contrib_etags),
            },
        )

    def run(self, since: date, *, fixtures: bool = False, dry_run: bool = False) -> RunResult:
        """Satisfy BaseScraper by delegating to the shared runner.

        Args:
            since: Backfill start date.
            fixtures: Replay checked-in fixtures instead of live HTTP.
            dry_run: Skip all warehouse contact.

        Returns:
            The run summary.
        """
        del fixtures
        return execute_run(self, build_deps(SOURCE, dry_run=dry_run), since)

    def _lookup_stubs(self, full_names: tuple[str, ...]) -> list[RepoStub]:
        """Resolve an explicit repo list via REST, skipping missing repos.

        Args:
            full_names: 'owner/repo' names (deduplicated, order kept).

        Returns:
            Stubs for the repos that exist.
        """
        stubs: list[RepoStub] = []
        for full_name in dict.fromkeys(full_names):
            payload = self._deps.rest.repo(full_name)
            if payload is None:
                self._deps.log.warning("explicit repo not found", full_name=full_name)
                continue
            node_id = get_str(payload, "node_id")
            repo_id = get_int(payload, "id")
            if node_id is None or repo_id is None:
                continue
            stubs.append(
                RepoStub(
                    node_id=node_id,
                    repo_id=repo_id,
                    full_name=get_str(payload, "full_name") or full_name,
                    stars=get_int(payload, "stargazers_count") or 0,
                )
            )
        self._deps.log.info("explicit repos resolved", requested=len(full_names), found=len(stubs))
        return stubs

    def _hydrate_batch(
        self,
        chunk: Sequence[RepoStub],
        commits_since: str | None,
        readme_etags: dict[str, str],
        contrib_etags: dict[str, str],
        cached: dict[int, str],
    ) -> RawBatch:
        results, failures = self._deps.gql.hydrate_repos(chunk, commits_since)
        items: list[dict[str, Json]] = []
        for stub in chunk:
            repo = results.get(stub.full_name)
            if repo is None:
                continue
            items.extend(self._repo_items(stub, repo, readme_etags, cached))
            self._collect_core(stub, contrib_etags)
        items.extend(_error_item(failure) for failure in failures)
        return RawBatch(source=SOURCE, items=tuple(items))

    def _repo_items(
        self,
        stub: RepoStub,
        repo: dict[str, Json],
        readme_etags: dict[str, str],
        cached: dict[int, str],
    ) -> list[dict[str, Json]]:
        readme_md, etag = self._readme(stub, readme_etags, cached)
        payload = dict(repo)
        if readme_md is not None:
            payload["readme_md"] = readme_md
        payload["funded_signals"] = list[Json](funded_signals(repo, readme_md))
        scraped_at = self._deps.clock().isoformat()
        repo_item: dict[str, Json] = {
            "kind": "repo",
            "repo_id": stub.repo_id,
            "full_name": stub.full_name,
            "payload": payload,
            "etag": etag,
            "source_url": f"https://github.com/{stub.full_name}",
            "scraped_at": scraped_at,
        }
        return [repo_item, *self._commit_items(stub, repo, scraped_at)]

    def _readme(
        self, stub: RepoStub, readme_etags: dict[str, str], cached: dict[int, str]
    ) -> tuple[str | None, str | None]:
        old_etag = readme_etags.get(str(stub.repo_id))
        response = self._deps.rest.readme(stub.full_name, etag=old_etag)
        if response.status == NOT_MODIFIED:
            stored = cached.get(stub.repo_id)
            if stored is not None and old_etag is not None:
                self._new_readme_etags[str(stub.repo_id)] = old_etag
                return stored, old_etag
            response = self._deps.rest.readme(stub.full_name, etag=None)
        if response.status == NOT_FOUND_STATUS:
            return None, None
        text = response.body[:README_MAX_BYTES].decode("utf-8", errors="replace")
        if response.etag is not None:
            self._new_readme_etags[str(stub.repo_id)] = response.etag
        return text, response.etag

    def _commit_items(
        self, stub: RepoStub, repo: dict[str, Json], scraped_at: str
    ) -> list[dict[str, Json]]:
        history = get_map(get_map(get_map(repo, "defaultBranchRef"), "target"), "history")
        items: list[dict[str, Json]] = []
        for node_value in get_list(history, "nodes"):
            node = as_mapping(node_value)
            sha = get_str(node, "oid")
            if sha is None:
                continue
            author = get_map(node, "author")
            user = get_map(author, "user")
            self._collect_email(get_str(user, "login"), get_str(author, "email"), sha)
            items.append(
                {
                    "kind": "commit",
                    "repo_id": stub.repo_id,
                    "sha": sha,
                    "author_user_id": get_int(user, "databaseId"),
                    "payload": node,
                    "source_url": f"https://github.com/{stub.full_name}/commit/{sha}",
                    "scraped_at": scraped_at,
                }
            )
        return items

    def _collect_email(self, login: str | None, email: str | None, sha: str) -> None:
        if login is None or email is None or email.endswith(NOREPLY_SUFFIX):
            return
        self._emails.setdefault(login, []).append({"email": email, "sha": sha})

    def _collect_core(self, stub: RepoStub, contrib_etags: dict[str, str]) -> None:
        old_etag = contrib_etags.get(str(stub.repo_id))
        response = self._deps.rest.contributors(stub.full_name, etag=old_etag)
        if response.status == NOT_MODIFIED and old_etag is not None:
            self._new_contrib_etags[str(stub.repo_id)] = old_etag
            return
        if response.status == NOT_FOUND_STATUS or not response.body:
            return
        stats = _contributor_stats(response.json())
        self._core_logins.update(stat.login for stat in core_contributors(stats))
        if response.etag is not None:
            self._new_contrib_etags[str(stub.repo_id)] = response.etag

    def _profile_batch(self, logins: Sequence[str]) -> RawBatch:
        results, failures = self._deps.gql.user_profiles(logins)
        items: list[dict[str, Json]] = []
        for login in logins:
            profile = results.get(login)
            if profile is None:
                continue
            payload = dict(profile)
            emails = sorted(
                self._emails.get(login, []),
                key=lambda entry: (str(entry["email"]), str(entry["sha"])),
            )
            payload["candidate_emails"] = list[Json](emails)
            items.append(
                {
                    "kind": "user",
                    "user_id": get_int(profile, "databaseId"),
                    "login": login,
                    "payload": payload,
                    "source_url": f"https://github.com/{login}",
                    "scraped_at": self._deps.clock().isoformat(),
                }
            )
        items.extend(_error_item(failure) for failure in failures)
        return RawBatch(source=SOURCE, items=tuple(items))


def _str_map(value: object) -> dict[str, str]:
    return {key: entry for key, entry in as_mapping(value).items() if isinstance(entry, str)}


def _contributor_stats(body: object) -> list[ContributorStat]:
    stats: list[ContributorStat] = []
    for entry_value in as_list(body):
        entry = as_mapping(entry_value)
        login = get_str(entry, "login")
        if login is None:
            continue
        stats.append(
            ContributorStat(
                login=login,
                user_id=get_int(entry, "id") or 0,
                contributions=get_int(entry, "contributions") or 0,
                user_type=get_str(entry, "type") or "User",
            )
        )
    return stats
