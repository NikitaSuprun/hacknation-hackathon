# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Participant CV toolkit: fetch the PDF, store it, extract text and facts.

CV handling is deliberately isolated from the JSON scrape so a broken PDF, a
slow host, or a model outage can never stall people/projects ingest: every
step degrades to None and the raw model output survives in bronze when JSON
parsing fails. The volume path is deterministic from user_id because the
erasure cascade must be able to find and delete the stored PDF later.
"""

import hashlib
import io
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol, cast

import httpx
from databricks.sdk import WorkspaceClient
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from contracts.models import Json, SinkRow, SinkValue
from scrapers.common.http import HttpClient, HttpStatusError
from tools.db import content_hash
from tools.llm import response_format
from tools.warehouse import Warehouse

__all__ = [
    "AI_QUERY_SQL",
    "CV_BUCKET",
    "DEFAULT_LLM_ENDPOINT",
    "ENDPOINT_ENV_VAR",
    "EXTRACTION_PROMPT",
    "MAX_CV_CHARS",
    "VOLUME_PATH_TEMPLATE",
    "CvDocument",
    "CvExtraction",
    "IngestStamp",
    "build_prompt",
    "cv_row",
    "extract_facts",
    "extract_text",
    "fetch_cv",
    "llm_endpoint",
    "upload_pdf",
    "volume_path",
]

# CVs live on external hosts, not the showcase API; a separate bucket keeps
# their pacing independent of people/project calls on the shared client.
CV_BUCKET: Final[str] = "hacknation_cv"
# LLM context hygiene: a CV longer than this is cut, not rejected.
MAX_CV_CHARS: Final[int] = 20_000
# The erasure-cascade contract: the stored PDF is findable from user_id alone.
VOLUME_PATH_TEMPLATE: Final[str] = "/Volumes/{catalog}/ops/cv/hacknation/{user_id}.pdf"

DEFAULT_LLM_ENDPOINT: Final[str] = "databricks-claude-sonnet-4-6"
ENDPOINT_ENV_VAR: Final[str] = "HACKNATION_CV_ENDPOINT"
# Values travel as named parameters; CV text must never be interpolated into SQL.
AI_QUERY_SQL: Final[str] = (
    "SELECT ai_query(:endpoint, :prompt, responseFormat => :response_format) AS extracted"
)

# Mirrors the gold.interview.extracted vocabulary (education[], career-like experience[]).
EXTRACTION_PROMPT: Final[str] = (
    "Extract structured facts from the CV text below. Years are integers. Every "
    "unknown field must be null. Never invent facts that are not stated in the "
    "CV.\nCV text:\n"
)

_YEAR: Final[dict[str, Json]] = {"type": ["integer", "null"]}
_TEXT: Final[dict[str, Json]] = {"type": ["string", "null"]}
# The shape the prompt used to describe in prose; ai_query constrains the model
# to it, so an unparseable answer means the endpoint failed, not the wording.
EXTRACTION_SCHEMA: Final[dict[str, Json]] = {
    "type": "object",
    "properties": {
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "institution": {"type": "string"},
                    "degree": _TEXT,
                    "field": _TEXT,
                    "start_year": _YEAR,
                    "end_year": _YEAR,
                },
                "required": ["institution"],
            },
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "organization": {"type": "string"},
                    "title": _TEXT,
                    "start_year": _YEAR,
                    "end_year": _YEAR,
                    "summary": _TEXT,
                },
                "required": ["organization"],
            },
        },
        "skills": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["education", "experience", "skills"],
}

# Signed storage URLs often serve PDFs as octet-stream.
_PDF_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {"application/pdf", "application/octet-stream"}
)
_HTTP_OK: Final[int] = 200


@dataclass(frozen=True, slots=True)
class CvDocument:
    """One participant CV as fetched from the showcase profile."""

    user_id: str
    cv_url: str
    pdf_bytes: bytes


@dataclass(frozen=True, slots=True)
class CvExtraction:
    """Outcome of the LLM extraction over one CV text."""

    extracted: Json | None
    raw_response: str | None
    model: str


@dataclass(frozen=True, slots=True)
class IngestStamp:
    """Provenance columns shared by every bronze row of one run."""

    scraped_at: datetime
    ingested_at: datetime
    run_id: str


class _ParamCursor(Protocol):
    """The parameter-binding cursor surface the ai_query statement needs.

    The vendor cursor accepts named :param markers; the deliberately minimal
    CursorLike seam omits them, so the widening lives here.
    """

    def execute(self, operation: str, parameters: dict[str, str]) -> object:
        """Run one parameterized statement."""
        ...

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return all rows of the last statement."""
        ...


def volume_path(catalog: str, user_id: str) -> str:
    """The deterministic UC Volume path for one participant's CV PDF.

    Args:
        catalog: Target catalog (dealflow | dealflow_dev).
        user_id: Hack Nation participant id.

    Returns:
        The volume path the PDF is stored at (and erased from).
    """
    return VOLUME_PATH_TEMPLATE.format(catalog=catalog, user_id=user_id)


def llm_endpoint() -> str:
    """The ai_query endpoint to use, overridable per environment.

    Returns:
        HACKNATION_CV_ENDPOINT when set, else DEFAULT_LLM_ENDPOINT.
    """
    return os.environ.get(ENDPOINT_ENV_VAR, DEFAULT_LLM_ENDPOINT)


def _content_type(headers: Mapping[str, str]) -> str:
    """The content-type header value, looked up case-insensitively."""
    for key, value in headers.items():
        if key.lower() == "content-type":
            return value
    return ""


def fetch_cv(url: str, *, http: HttpClient) -> bytes | None:
    """Fetch one CV PDF; a failed fetch must never crash the run.

    Args:
        url: The participant's cv_url.
        http: The shared client (bucket 'hacknation_cv' paces CV hosts).

    Returns:
        The PDF body, or None on transport errors, non-200 status, non-PDF
        content type, or an empty body.
    """
    try:
        response = http.get(url, bucket=CV_BUCKET)
    except (HttpStatusError, httpx.HTTPError, httpx.InvalidURL):
        return None
    content_type = _content_type(response.headers).split(";")[0].strip().lower()
    if response.status != _HTTP_OK or content_type not in _PDF_CONTENT_TYPES:
        return None
    return response.body or None


def extract_text(pdf_bytes: bytes) -> str | None:
    """Extract page text from a PDF, capped for LLM context hygiene.

    Args:
        pdf_bytes: The fetched PDF body.

    Returns:
        Joined page text (at most MAX_CV_CHARS), or None when the bytes are
        not a readable PDF or carry no text.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() for page in reader.pages)
    except PyPdfError:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    return stripped[:MAX_CV_CHARS]


def build_prompt(cv_text: str) -> str:
    """The full extraction prompt for one CV text.

    Args:
        cv_text: Extracted CV text (already capped at MAX_CV_CHARS).

    Returns:
        EXTRACTION_PROMPT with the CV text appended.
    """
    return f"{EXTRACTION_PROMPT}{cv_text}"


def _strip_fences(raw: str) -> str:
    """Drop a wrapping markdown code fence; models love ```json wrappers."""
    text = raw.strip()
    if not text.startswith("```"):
        return text
    text = text.removeprefix("```json").removeprefix("```")
    return text.removesuffix("```").strip()


def extract_facts(
    cv_text: str, *, warehouse: Warehouse, endpoint: str
) -> tuple[Json | None, str | None]:
    """LLM-extract structured CV facts via the warehouse ai_query function.

    Args:
        cv_text: Extracted CV text.
        warehouse: Connection factory for the SQL warehouse.
        endpoint: Serving endpoint name passed to ai_query.

    Returns:
        (parsed, None) when the response is valid JSON, else (None, raw
        response) so the raw model output still lands in bronze.
    """
    with warehouse.cursor() as cursor:
        # Same double-cast as tools.warehouse: widen the minimal seam to the
        # vendor cursor's parameter binding without touching shared code.
        param_cursor = cast("_ParamCursor", cast("object", cursor))
        param_cursor.execute(
            AI_QUERY_SQL,
            {
                "endpoint": endpoint,
                "prompt": build_prompt(cv_text),
                "response_format": response_format(EXTRACTION_SCHEMA),
            },
        )
        rows = param_cursor.fetchall()
    cell = rows[0][0] if rows else None
    raw = "" if cell is None else str(cell)
    try:
        parsed: Json = json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        return None, raw
    return parsed, None


def cv_row(
    document: CvDocument,
    pdf_volume_path: str,
    text: str | None,
    extraction: CvExtraction,
    *,
    stamp: IngestStamp,
) -> SinkRow:
    """Shape one bronze.hacknation_cvs_raw row; columns mirror the DDL exactly.

    Args:
        document: The fetched CV (user_id and cv_url are recorded, bytes are not).
        pdf_volume_path: Where upload_pdf stored the PDF.
        text: Extracted CV text, or None when unreadable.
        extraction: LLM extraction outcome for that text.
        stamp: Run provenance for the bronze envelope.

    Returns:
        A row matching the bronze.hacknation_cvs_raw column set.
    """
    text_sha256 = None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()
    payload: dict[str, Json] = {
        "cv_url": document.cv_url,
        "volume_path": pdf_volume_path,
        "text_sha256": text_sha256,
        "text_chars": None if text is None else len(text),
        "extracted": extraction.extracted,
        "model": extraction.model,
    }
    if extraction.extracted is None:
        # Keep the unparseable model output for replay; drop it once parsed.
        payload["raw_response"] = extraction.raw_response
    return {
        "user_id": document.user_id,
        # Json is a semantic subset of SinkValue; the cast bridges the
        # container invariance the type system cannot see through.
        "payload": cast("SinkValue", payload),
        "content_hash": content_hash(payload),
        "source_url": document.cv_url,
        "scraped_at": stamp.scraped_at,
        "ingested_at": stamp.ingested_at,
        "scrape_run_id": stamp.run_id,
    }


def upload_pdf(client: WorkspaceClient, path: str, pdf_bytes: bytes) -> None:
    """Store one CV PDF at its UC Volume path (idempotent overwrite).

    Args:
        client: Workspace client owning the Files API.
        path: Target path from volume_path().
        pdf_bytes: The fetched PDF body.
    """
    client.files.upload(path, io.BytesIO(pdf_bytes), overwrite=True)
