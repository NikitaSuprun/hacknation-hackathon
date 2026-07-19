# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Smoke: the fixtures app builds in-process and serves /healthz, /v1/ranking,
and the static SPA shell."""

from app.deps import build_fixture_deps
from fixtures import build
from scrapers.common.jsonutil import get_str
from tests.app.conftest import AppClient


def test_fixtures_app_smokes_end_to_end() -> None:
    client = AppClient(build_fixture_deps(base_url="http://testserver"))
    assert client.get("/healthz").body["status"] == "ok"
    token = client.post("/v1/login", payload={"password": "demo"}).body["token"]
    ranking = client.get("/v1/ranking", headers={"Authorization": f"Bearer {token}"})
    assert get_str(ranking.items("ventures")[0], "venture_id") == build.GRASP_VENTURE


def test_static_spa_is_served_at_the_root() -> None:
    client = AppClient(build_fixture_deps(base_url="http://testserver"))
    index = client.get("/")
    assert index.status_code == 200
    assert "Venture Hunt" in index.text
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200
