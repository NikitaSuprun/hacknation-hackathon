# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""HN1: the client's endpoints, replayed fixtures, and the content-type guard."""

import pytest

from scrapers.common.http import HttpClient, Timing, TokenBucket
from scrapers.common.jsonutil import get_list, get_str
from sources.hacknation.client import BUCKET, HacknationClient, NotJsonResponseError
from sources.hacknation.replay import SPA_PROJECT_ID, fixture_transport


def _client() -> HacknationClient:
    timing = Timing(clock=lambda: 0.0, sleep=lambda _seconds: None)
    http = HttpClient(
        user_agent="dealflow-tests",
        headers={},
        buckets={BUCKET: TokenBucket(1.0, 100.0, timing=timing)},
        transport=fixture_transport(),
        timing=timing,
    )
    return HacknationClient(http)


def test_people_replays_the_committed_wire_fixture() -> None:
    data = _client().people()
    people = get_list(data, "people")
    assert len(people) == 6
    first = people[0]
    assert isinstance(first, dict)
    assert get_str(first, "user_id") == "hn-lena-01"
    assert get_str(first, "display_name") == "Léna Fischer"


def test_project_detail_replays_with_github_url() -> None:
    detail = _client().project("hnp-grasp-01")
    assert get_str(detail, "title") == "GraspFM Hackathon Demo"
    assert get_str(detail, "githubUrl") == "https://github.com/grasplab/grasp-anything"


def test_spa_fallback_raises_the_typed_guard_error() -> None:
    # Netlify answers unknown routes with the index page and HTTP 200; the
    # content-type guard must refuse to parse it.
    with pytest.raises(NotJsonResponseError, match="application/json"):
        _client().project(SPA_PROJECT_ID)
