# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""HacknationNormalizer: bronze Hack Nation rows to person_source_records.

The derivation itself lives in er.normalize.hacknation_psrs (registered in
the stage-0 extractor set, exactly like the other sources) so that fixture
bronze rows normalize byte-exact into the committed PSR fixtures; this module
adapts it onto the contracts.interfaces.SourceNormalizer seam.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Final, cast

from contracts.models import BronzeRecord, Json, PersonSourceRecord, SinkValue
from er.normalize import hacknation_psrs, hacknation_user_id
from scrapers.common.jsonutil import get_map
from sources.hacknation.ingest import PEOPLE_TABLE, PROJECTS_TABLE

Row = dict[str, Json]

_TABLES: Final[frozenset[str]] = frozenset({PEOPLE_TABLE, PROJECTS_TABLE})


def _as_json_row(row: Mapping[str, SinkValue]) -> Row:
    """Bridge a sink-shaped bronze row into the JSON row shape.

    Temporals become ISO strings; payload trees are Json by construction
    (they were parsed from the wire), so the cast only reverses as_sink.
    """
    bridged: Row = {}
    for key, value in row.items():
        if isinstance(value, datetime | date):
            bridged[key] = value.isoformat()
        else:
            bridged[key] = cast("Json", value)
    return bridged


class HacknationNormalizer:
    """SourceNormalizer for source='hacknation' (see contracts.interfaces)."""

    def __init__(self, project_rows: Sequence[Row]) -> None:
        """Bind the project bronze rows used for cross-enrichment.

        Args:
            project_rows: bronze.hacknation_projects_raw rows; author/team
                entries enrich the people-list PSRs (linkedinUrl, keywords).
        """
        self._projects: Final[list[Row]] = list(project_rows)

    def to_psr(self, row: BronzeRecord) -> list[PersonSourceRecord]:
        """Extract person source records from one bronze row.

        A people row yields exactly one PSR (enriched from the bound project
        rows). A project row yields fallback PSRs for its author/team members
        from project-side fields alone; when the people listing is ingested
        too, its richer rows MERGE over these (same deterministic psr_id).

        Args:
            row: One bronze.hacknation_people_raw or _projects_raw record.

        Returns:
            The derived records; empty for foreign tables.
        """
        if row.table not in _TABLES:
            return []
        json_row = _as_json_row(row.row)
        if row.table == PEOPLE_TABLE:
            user_id = hacknation_user_id(get_map(json_row, "payload"))
            return [
                record
                for record in hacknation_psrs([json_row], self._projects)
                if record.source_key == user_id
            ]
        return hacknation_psrs([], [json_row])
