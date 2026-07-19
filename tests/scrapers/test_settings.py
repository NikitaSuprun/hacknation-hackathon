# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Settings fail fast; the offline CI path reads no environment at all."""

from pathlib import Path
from typing import Final

import pytest

from scrapers.common.settings import (
    load_scraper_settings,
    offline_scraper_settings,
    require_key,
)
from scrapers.common.sink import NullSink, build_deps
from scrapers.common.state import MemoryStateStore
from tools.settings import MissingConfigError

SCRAPER_ENV_KEYS: Final[tuple[str, ...]] = (
    "SCRAPER_CONTACT_EMAIL",
    "GITHUB_TOKEN",
    "OPENALEX_API_KEY",
    "S2_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction] - pytest collects autouse fixtures
    for key in SCRAPER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_missing_contact_email_fails_fast(tmp_path: Path) -> None:
    # An explicit empty dotenv keeps the test hermetic when a real .env exists.
    empty = tmp_path / "empty.env"
    empty.write_text("")
    with pytest.raises(MissingConfigError, match="SCRAPER_CONTACT_EMAIL"):
        load_scraper_settings(env_file=empty)


def test_source_keys_stay_optional(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    empty = tmp_path / "empty.env"
    empty.write_text("")
    monkeypatch.setenv("SCRAPER_CONTACT_EMAIL", "dev@example.org")
    settings = load_scraper_settings(env_file=empty)
    assert settings.contact_email == "dev@example.org"
    assert settings.github_token is None
    assert settings.openalex_api_key is None
    assert settings.s2_api_key is None
    assert settings.user_agent == "dealflow-scraper/0.1 (+mailto:dev@example.org)"


def test_offline_settings_need_no_env() -> None:
    settings = offline_scraper_settings()
    assert "mailto:" in settings.user_agent
    assert settings.github_token is None


def test_require_key_raises_on_absent_value() -> None:
    with pytest.raises(MissingConfigError, match="GITHUB_TOKEN"):
        require_key(None, "GITHUB_TOKEN")
    assert require_key("tok", "GITHUB_TOKEN") == "tok"


def test_dry_run_deps_touch_no_credentials() -> None:
    # No Databricks env is set (autouse fixture); a warehouse path would raise.
    deps = build_deps("github", dry_run=True)
    assert isinstance(deps.sink, NullSink)
    assert isinstance(deps.state, MemoryStateStore)
    assert deps.warehouse is None
