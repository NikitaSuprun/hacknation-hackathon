# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Offline tests for the CV toolkit: fixture PDF, mocked HTTP, golden bronze rows."""

import json
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Final, cast

import httpx
import pytest

from contracts.models import Json
from scrapers.common.http import HttpClient, TokenBucket
from scrapers.hacknation import cv
from scrapers.hacknation.replay import CV_PDF
from tests.scrapers.conftest import FakeTime
from tools.db import SUPPRESSION_RULES, SuppressionRule, content_hash
from tools.llm import response_format
from tools.warehouse import Warehouse

_CV_URL: Final[str] = "https://cdn.example.org/cv/u1.pdf"
_USER_AGENT: Final[str] = "dealflow-scraper/0.1 (+mailto:test@example.invalid)"
_SCRAPED_AT: Final[datetime] = datetime(2026, 7, 19, 8, 0, tzinfo=UTC)
_INGESTED_AT: Final[datetime] = datetime(2026, 7, 19, 8, 5, tzinfo=UTC)
_STAMP: Final[cv.IngestStamp] = cv.IngestStamp(
    scraped_at=_SCRAPED_AT, ingested_at=_INGESTED_AT, run_id="run-1"
)


class _FakeCursor:
    cell: object
    calls: list[tuple[str, dict[str, str]]]

    def __init__(self, cell: object) -> None:
        self.cell = cell
        self.calls = []

    def execute(self, operation: str, parameters: dict[str, str]) -> object:
        self.calls.append((operation, parameters))
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return [(self.cell,)]

    def close(self) -> None:
        return


class _FakeWarehouse:
    cursor_obj: _FakeCursor

    def __init__(self, cell: object) -> None:
        self.cursor_obj = _FakeCursor(cell)

    @contextmanager
    def cursor(self) -> Generator[_FakeCursor]:
        yield self.cursor_obj


def _as_warehouse(fake: _FakeWarehouse) -> Warehouse:
    return cast("Warehouse", cast("object", fake))


def _http(handler: Callable[[httpx.Request], httpx.Response]) -> HttpClient:
    time = FakeTime()
    return HttpClient(
        user_agent=_USER_AGENT,
        headers={},
        buckets={cv.CV_BUCKET: TokenBucket(1000.0, 10.0, timing=time.timing())},
        transport=httpx.MockTransport(handler),
        timing=time.timing(),
    )


def test_extract_text_reads_the_fixture_pdf() -> None:
    text = cv.extract_text(CV_PDF.read_bytes())
    assert text is not None
    assert "Selin Aydin" in text
    assert "KTH" in text


def test_extract_text_returns_none_for_non_pdf_bytes() -> None:
    assert cv.extract_text(b"not a pdf") is None


def test_volume_path_is_deterministic_from_user_id() -> None:
    assert cv.volume_path("dealflow_dev", "u1") == "/Volumes/dealflow_dev/ops/cv/hacknation/u1.pdf"


def test_build_prompt_embeds_cv_text_and_states_the_extraction_rules() -> None:
    """The shape rides on the response format; the prompt carries the rules."""
    prompt = cv.build_prompt("EXPERIENCE AT KTH")
    assert prompt.endswith("EXPERIENCE AT KTH")
    assert "null" in prompt
    assert "Never invent facts" in prompt


def test_ai_query_constants_are_golden() -> None:
    assert cv.AI_QUERY_SQL == (
        "SELECT ai_query(:endpoint, :prompt, responseFormat => :response_format) AS extracted"
    )
    assert cv.DEFAULT_LLM_ENDPOINT == "databricks-claude-sonnet-4-6"


def test_extraction_schema_covers_the_documented_shape() -> None:
    properties = cv.EXTRACTION_SCHEMA["properties"]
    assert isinstance(properties, dict)
    assert set(properties) == {"education", "experience", "skills"}
    education = properties["education"]
    assert isinstance(education, dict)
    items = education["items"]
    assert isinstance(items, dict)
    assert items["required"] == ["institution"]


def test_llm_endpoint_is_env_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HACKNATION_CV_ENDPOINT", raising=False)
    assert cv.llm_endpoint() == cv.DEFAULT_LLM_ENDPOINT
    monkeypatch.setenv("HACKNATION_CV_ENDPOINT", "databricks-claude-haiku-4-5")
    assert cv.llm_endpoint() == "databricks-claude-haiku-4-5"


def test_extract_facts_strips_markdown_fences_and_binds_parameters() -> None:
    fake = _FakeWarehouse('```json\n{"skills": ["ros"]}\n```')
    extracted, raw = cv.extract_facts("cv text", warehouse=_as_warehouse(fake), endpoint="ep")
    assert extracted == {"skills": ["ros"]}
    assert raw is None
    assert fake.cursor_obj.calls == [
        (
            cv.AI_QUERY_SQL,
            {
                "endpoint": "ep",
                "prompt": cv.build_prompt("cv text"),
                "response_format": response_format(cv.EXTRACTION_SCHEMA),
            },
        )
    ]


def test_extract_facts_sends_the_schema_as_a_response_format() -> None:
    fake = _FakeWarehouse('{"education": [], "experience": [], "skills": []}')
    cv.extract_facts("cv text", warehouse=_as_warehouse(fake), endpoint="ep")
    sent = json.loads(fake.cursor_obj.calls[0][1]["response_format"])
    assert sent["type"] == "json_schema"
    assert sent["json_schema"]["schema"] == cv.EXTRACTION_SCHEMA


def test_extract_facts_returns_raw_response_on_invalid_json() -> None:
    fake = _FakeWarehouse("Sorry, I cannot help with that.")
    extracted, raw = cv.extract_facts("cv text", warehouse=_as_warehouse(fake), endpoint="ep")
    assert extracted is None
    assert raw == "Sorry, I cannot help with that."


def test_cv_row_matches_the_bronze_envelope_golden() -> None:
    document = cv.CvDocument(user_id="u1", cv_url=_CV_URL, pdf_bytes=b"%PDF")
    extraction = cv.CvExtraction(
        extracted={"skills": ["ros"]}, raw_response=None, model="databricks-claude-sonnet-4-6"
    )
    row = cv.cv_row(
        document, cv.volume_path("dealflow_dev", "u1"), "Aisha Rahman", extraction, stamp=_STAMP
    )
    expected_payload: dict[str, Json] = {
        "cv_url": _CV_URL,
        "volume_path": "/Volumes/dealflow_dev/ops/cv/hacknation/u1.pdf",
        "text_sha256": "10ba71af58b6391482378602b4a5cd215f516e6f7d4b2cadf039523c21817381",
        "text_chars": 12,
        "extracted": {"skills": ["ros"]},
        "model": "databricks-claude-sonnet-4-6",
    }
    assert row == {
        "user_id": "u1",
        "payload": expected_payload,
        "content_hash": content_hash(expected_payload),
        "source_url": _CV_URL,
        "scraped_at": _SCRAPED_AT,
        "ingested_at": _INGESTED_AT,
        "scrape_run_id": "run-1",
    }


def test_cv_row_keeps_raw_response_only_when_unparsed() -> None:
    document = cv.CvDocument(user_id="u1", cv_url=_CV_URL, pdf_bytes=b"%PDF")
    extraction = cv.CvExtraction(extracted=None, raw_response="not json", model="m")
    row = cv.cv_row(document, "/Volumes/x", None, extraction, stamp=_STAMP)
    payload = row["payload"]
    assert isinstance(payload, dict)
    assert payload["raw_response"] == "not json"
    assert payload["text_sha256"] is None
    assert payload["text_chars"] is None


def test_fetch_cv_returns_pdf_bytes_with_the_shared_user_agent() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4 fake"
        )

    assert cv.fetch_cv(_CV_URL, http=_http(handler)) == b"%PDF-1.4 fake"
    assert seen[0].headers["user-agent"] == _USER_AGENT


def test_fetch_cv_accepts_octet_stream() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "application/octet-stream"}, content=b"%PDF-1.4"
        )

    assert cv.fetch_cv(_CV_URL, http=_http(handler)) == b"%PDF-1.4"


def test_fetch_cv_returns_none_on_error_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"content-type": "application/pdf"}, content=b"gone")

    assert cv.fetch_cv(_CV_URL, http=_http(handler)) is None


def test_fetch_cv_returns_none_on_non_pdf_content_type() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html></html>")

    assert cv.fetch_cv(_CV_URL, http=_http(handler)) is None


def test_fetch_cv_returns_none_on_empty_body() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"")

    assert cv.fetch_cv(_CV_URL, http=_http(handler)) is None


def test_cvs_table_is_registered_for_erasure_suppression() -> None:
    assert SUPPRESSION_RULES["bronze.hacknation_cvs_raw"] == SuppressionRule(
        "hacknation", None, "user_id"
    )
