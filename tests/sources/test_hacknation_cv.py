"""HN4: the CV ingestion gate is off by default and never fetches today."""

from sources.hacknation.cv import (
    CV_INGESTION_ENV,
    STATUS_DISABLED,
    STATUS_NO_URL,
    STATUS_PENDING_SIGNOFF,
    cv_ingestion_enabled,
    fetch_cv,
)


def test_gate_defaults_off_and_parses_truthy_values() -> None:
    assert cv_ingestion_enabled(env={}) is False
    assert cv_ingestion_enabled(env={CV_INGESTION_ENV: ""}) is False
    assert cv_ingestion_enabled(env={CV_INGESTION_ENV: "0"}) is False
    assert cv_ingestion_enabled(env={CV_INGESTION_ENV: "1"}) is True
    assert cv_ingestion_enabled(env={CV_INGESTION_ENV: "True"}) is True


def test_disabled_gate_returns_the_typed_noop_result() -> None:
    result = fetch_cv("https://cdn.hack-nation.ai/cv/hn-noah-01.pdf", enabled=False)
    assert result.status == STATUS_DISABLED
    assert result.cv_url == "https://cdn.hack-nation.ai/cv/hn-noah-01.pdf"
    assert CV_INGESTION_ENV in result.detail


def test_enabled_gate_still_never_fetches_pending_signoff() -> None:
    assert fetch_cv(None, enabled=True).status == STATUS_NO_URL
    result = fetch_cv("https://cdn.hack-nation.ai/cv/hn-noah-01.pdf", enabled=True)
    assert result.status == STATUS_PENDING_SIGNOFF
