"""OpenAlex enrichment: DOI batching, abstract reconstruction, promotions."""

from datetime import UTC, date, datetime
from typing import Final

import httpx

from contracts.models import Json
from scrapers.common.http import HttpClient, TokenBucket
from scrapers.common.jsonutil import as_mapping
from scrapers.common.log import get_logger
from scrapers.papers.models import PendingPaper
from scrapers.papers.normalize import (
    arxiv_id_from_work,
    openalex_work_to_row,
    reconstruct_abstract,
)
from scrapers.papers.openalex_client import (
    OpenAlexClient,
    WarehousePendingWorks,
    lookup_doi,
)
from tests.scrapers.conftest import FakeTime
from tests.scrapers.test_state import FakeRunner

NOW: Final[datetime] = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


def test_lookup_doi_prefers_journal_doi() -> None:
    assert lookup_doi(PendingPaper(arxiv_id="2506.11111", doi="10.1234/Foo.BAR")) == (
        "10.1234/foo.bar"
    )
    assert lookup_doi(PendingPaper(arxiv_id="2506.11111", doi=None)) == (
        "10.48550/arxiv.2506.11111"
    )


def test_reconstruct_abstract_handles_repeats_and_order() -> None:
    inverted: dict[str, Json] = {
        "the": [0, 3],
        "cat": [1],
        "sat": [2],
        "mat": [4],
    }
    assert reconstruct_abstract(inverted) == "the cat sat the mat"


def test_arxiv_id_from_work_via_doi_and_landing() -> None:
    via_doi: dict[str, Json] = {"doi": "https://doi.org/10.48550/arXiv.2506.11111"}
    assert arxiv_id_from_work(via_doi) == "2506.11111"
    via_landing: dict[str, Json] = {
        "doi": "https://doi.org/10.1234/journal.2026.1",
        "locations": [{"landing_page_url": "https://arxiv.org/abs/2507.22222v1"}],
    }
    assert arxiv_id_from_work(via_landing) == "2507.22222"
    assert arxiv_id_from_work({"doi": "https://doi.org/10.1234/x"}) is None


def test_work_to_row_promotions_and_selected_payload() -> None:
    work: dict[str, Json] = {
        "id": "https://openalex.org/W4400000001",
        "doi": "https://doi.org/10.48550/arxiv.2506.11111",
        "display_name": "GraspFM",
        "publication_date": "2026-06-12",
        "cited_by_count": 41,
        "abstract_inverted_index": {"We": [0], "present": [1]},
        "authorships": [
            {
                "author": {
                    "id": "https://openalex.org/A5000000001",
                    "display_name": "Léna Fischer",
                    "orcid": "https://orcid.org/0000-0002-1825-0097",
                },
                "author_position": "first",
                "institutions": [
                    {"display_name": "ETH Zürich", "ror": "https://ror.org/05a28rw58"}
                ],
            }
        ],
    }
    row = openalex_work_to_row(work, "run-0001", NOW, NOW)
    assert row["openalex_id"] == "W4400000001"
    assert row["doi"] == "10.48550/arxiv.2506.11111"
    assert row["arxiv_id"] == "2506.11111"
    payload = as_mapping(row["payload"])
    assert payload["title"] == "GraspFM"
    assert payload["cited_by_count"] == 41
    assert payload["abstract"] == "We present"
    assert payload["authorships"] == [
        {
            "author": {
                "display_name": "Léna Fischer",
                "id": "A5000000001",
                "orcid": "https://orcid.org/0000-0002-1825-0097",
            },
            "author_position": "first",
            "institutions": [{"display_name": "ETH Zürich", "ror": "https://ror.org/05a28rw58"}],
        }
    ]


def test_batching_splits_at_fifty_dois() -> None:
    seen: list[httpx.Request] = []
    time = FakeTime()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        dois = request.url.params["filter"].removeprefix("doi:").split("|")
        results = [
            {"id": f"https://openalex.org/W{index}", "doi": f"https://doi.org/{doi}"}
            for index, doi in enumerate(dois)
        ]
        return httpx.Response(200, json={"results": results})

    http = HttpClient(
        user_agent="test",
        headers={},
        buckets={"openalex": TokenBucket(1000.0, 10.0, timing=time.timing())},
        transport=httpx.MockTransport(handler),
        timing=time.timing(),
    )
    client = OpenAlexClient(http, "test-key", get_logger("test"))
    works = client.fetch_by_dois([f"10.48550/arxiv.2507.{index:05d}" for index in range(50)])
    assert len(works) == 50
    assert len(seen) == 1
    assert seen[0].url.params["per-page"] == "50"
    assert seen[0].url.params["api_key"] == "test-key"
    assert seen[0].url.params["filter"].startswith("doi:10.48550/arxiv.2507.00000|")


def test_warehouse_pending_anti_join_sql_is_golden() -> None:
    runner = FakeRunner([("2506.11111", None), ("2507.22222", "10.1234/x")])
    pending = WarehousePendingWorks(runner, "dealflow_dev").pending(date(2026, 6, 19), 500)
    assert pending == (
        PendingPaper(arxiv_id="2506.11111", doi=None),
        PendingPaper(arxiv_id="2507.22222", doi="10.1234/x"),
    )
    assert runner.statements == [
        "SELECT a.arxiv_id, CAST(a.payload:doi AS STRING) AS doi "
        "FROM dealflow_dev.bronze.arxiv_papers_raw a "
        "LEFT ANTI JOIN dealflow_dev.bronze.openalex_works_raw w "
        "ON w.arxiv_id = a.arxiv_id "
        "WHERE a.ingested_at >= '2026-06-19' "
        "LIMIT 500"
    ]
