# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Value objects shared by the scraper runner and the per-source packages."""

import json
from dataclasses import dataclass
from datetime import datetime

from contracts.models import BronzeRecord
from scrapers.common.tables import REJECTS_TABLE


@dataclass(frozen=True, slots=True)
class RateSnapshot:
    """One API rate-limit reading, parsed from x-ratelimit-* headers."""

    resource: str
    limit: int
    remaining: int
    reset_epoch: int


@dataclass(frozen=True, slots=True)
class FetchedResponse:
    """The HTTP surface scrapers consume; bodies stay raw bytes."""

    status: int
    body: bytes
    etag: str | None
    headers: dict[str, str]

    def json(self) -> object:
        """Parse the body as JSON.

        Returns:
            The decoded JSON value.
        """
        return json.loads(self.body)

    def text(self) -> str:
        """Decode the body as UTF-8, replacing invalid bytes.

        Returns:
            The decoded text.
        """
        return self.body.decode("utf-8", errors="replace")


@dataclass(frozen=True, slots=True)
class RejectRow:
    """A validation failure bound for bronze._rejects; runs never crash on these."""

    source: str
    natural_key: str
    error: str
    raw: str
    scrape_run_id: str
    ingested_at: datetime

    def to_bronze(self) -> BronzeRecord:
        """Render as a bronze record targeting the rejects table.

        Returns:
            The record in bronze._rejects column shape.
        """
        return BronzeRecord(
            table=REJECTS_TABLE,
            row={
                "source": self.source,
                "natural_key": self.natural_key,
                "error": self.error,
                "raw": self.raw,
                "scrape_run_id": self.scrape_run_id,
                "ingested_at": self.ingested_at,
            },
        )
