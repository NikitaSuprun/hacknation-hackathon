"""Validate the fixture JSONL offline: the T4 acceptance gate.

Checks referential integrity, enum/CHECK validity, the one-active-link and
one-is_latest invariants, unit-norm embeddings, payload-schema conformance,
bronze-to-PSR derivability through the normalizers, deterministic-id
recomputation through tools.ids, and the persona shapes each downstream
workstream builds against.
"""

import json
import math
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from contracts.models import Json
from contracts.validation import payload_errors
from fixtures.build import DATA_DIR
from fixtures.fake_embedding import EMBEDDING_DIM, cosine
from tools import ids, institutions, norm

Row = dict[str, Json]
Tables = dict[str, list[Row]]


class RowShapeError(TypeError):
    """Raised when a fixture line is not a JSON object."""

    def __init__(self, line: str) -> None:
        """Quote the offending line."""
        super().__init__(f"fixture line is not a JSON object: {line[:80]!r}")


def _parse_row(line: str) -> Row:
    """Parse one JSONL line into a row."""
    parsed: Json = json.loads(line)
    if not isinstance(parsed, dict):
        raise RowShapeError(line)
    return parsed


_PERSON_STATUSES: Final[frozenset[str]] = frozenset({"active", "merged", "erased"})
_LINK_STATUSES: Final[frozenset[str]] = frozenset({"active", "retracted"})
_VENTURE_STATUSES: Final[frozenset[str]] = frozenset(
    {"sourced", "scored", "shortlisted", "outreach", "interviewing", "passed", "archived"}
)
_ANCHOR_TYPES: Final[frozenset[str]] = frozenset(
    {"repo", "company", "paper_cluster", "hackathon_project"}
)
_OUTREACH_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "draft",
        "approved",
        "sent",
        "bounced",
        "replied",
        "consented",
        "declined",
        "interview_scheduled",
        "interview_started",
        "interviewed",
        "closed",
        "opted_out",
        "expired",
    }
)
_CONNECTION_TYPES: Final[frozenset[str]] = frozenset({"coauthor", "co_contributor", "co_officer"})
_INSTITUTION_KINDS: Final[frozenset[str]] = frozenset({"university", "company"})
_UNIT_NORM_TOLERANCE: Final[float] = 1e-6


def load_tables(data_dir: Path = DATA_DIR) -> Tables:
    """Parse every fixture JSONL file.

    Args:
        data_dir: The fixtures/data directory.

    Returns:
        Mapping of table name to rows.
    """
    tables: Tables = {}
    for path in sorted(data_dir.glob("*.jsonl")):
        lines = path.read_text(encoding="utf-8").splitlines()
        tables[path.stem] = [_parse_row(line) for line in lines if line]
    return tables


def _ids_of(tables: Tables, table: str, column: str) -> set[str]:
    return {value for row in tables.get(table, []) if isinstance(value := row.get(column), str)}


def _check_fk(tables: Tables) -> list[str]:
    persons = _ids_of(tables, "silver.person", "person_id")
    psrs = _ids_of(tables, "silver.person_source_record", "source_record_id")
    projects = _ids_of(tables, "silver.project", "project_id")
    publications = _ids_of(tables, "silver.publication", "publication_id")
    companies = _ids_of(tables, "silver.company", "company_id")
    ventures = _ids_of(tables, "gold.venture", "venture_id")
    theses = _ids_of(tables, "gold.thesis", "thesis_id")
    weights = _ids_of(tables, "gold.score_weights", "weights_id")
    scores = _ids_of(tables, "gold.venture_score", "score_id")
    outreaches = _ids_of(tables, "gold.outreach", "outreach_id")
    references: list[tuple[str, str, set[str]]] = [
        ("silver.person_source_link", "person_id", persons),
        ("silver.person_source_link", "source_record_id", psrs),
        ("silver.contribution", "project_id", projects),
        ("silver.contribution", "source_record_id", psrs),
        ("silver.authorship", "publication_id", publications),
        ("silver.authorship", "source_record_id", psrs),
        ("silver.officer", "company_id", companies),
        ("silver.officer", "source_record_id", psrs),
        ("silver.person_connection", "person_a_id", persons),
        ("silver.person_connection", "person_b_id", persons),
        ("gold.venture_member", "venture_id", ventures),
        ("gold.venture_member", "person_id", persons),
        ("gold.candidate_pool", "thesis_id", theses),
        ("gold.candidate_pool", "venture_id", ventures),
        ("gold.ideal_candidate", "thesis_id", theses),
        ("gold.score_weights", "thesis_id", theses),
        ("gold.venture_score", "venture_id", ventures),
        ("gold.venture_score", "thesis_id", theses),
        ("gold.venture_score", "weights_id", weights),
        ("gold.person_features", "person_id", persons),
        ("gold.venture_gaps", "venture_id", ventures),
        ("gold.memo", "venture_id", ventures),
        ("gold.outreach", "venture_id", ventures),
        ("gold.outreach", "person_id", persons),
        ("gold.interview", "outreach_id", outreaches),
        ("gold.interview", "venture_id", ventures),
        ("gold.interview", "person_id", persons),
        ("gold.interview", "rescore_score_id", scores),
        ("ops.er_review_queue", "source_record_id", psrs),
        ("ops.er_review_queue", "candidate_person_id", persons),
    ]
    errors: list[str] = []
    for table, column, valid in references:
        for row in tables.get(table, []):
            value = row.get(column)
            if value is not None and value not in valid:
                errors.append(f"{table}.{column}: dangling reference {value}")
    return errors


def _check_enums(tables: Tables) -> list[str]:
    enum_checks: list[tuple[str, str, frozenset[str]]] = [
        ("silver.person", "status", _PERSON_STATUSES),
        ("silver.person_source_link", "status", _LINK_STATUSES),
        ("gold.venture", "status", _VENTURE_STATUSES),
        ("gold.venture", "anchor_type", _ANCHOR_TYPES),
        ("gold.outreach", "status", _OUTREACH_STATUSES),
        ("silver.person_connection", "connection_type", _CONNECTION_TYPES),
        ("gold.institution_score", "kind", _INSTITUTION_KINDS),
    ]
    errors: list[str] = []
    for table, column, allowed in enum_checks:
        errors.extend(
            f"{table}.{column}: invalid value {row.get(column)!r}"
            for row in tables.get(table, [])
            if row.get(column) not in allowed
        )
    range_checks: list[tuple[str, str]] = [
        ("silver.person_source_link", "match_confidence"),
        ("gold.venture_score", "confidence"),
    ]
    for table, column in range_checks:
        errors.extend(
            f"{table}.{column}: out of range {row.get(column)!r}"
            for row in tables.get(table, [])
            if not _in_unit_range(row.get(column))
        )
    errors.extend(
        "silver.person_connection: person_a_id must sort before person_b_id"
        for row in tables.get("silver.person_connection", [])
        if not str(row.get("person_a_id")) < str(row.get("person_b_id"))
    )
    return errors


def _in_unit_range(value: object) -> bool:
    return isinstance(value, int | float) and 0.0 <= float(value) <= 1.0


def _check_link_invariants(tables: Tables) -> list[str]:
    errors: list[str] = []
    active_by_psr: dict[str, int] = {}
    for row in tables.get("silver.person_source_link", []):
        if row.get("status") == "active":
            key = str(row.get("source_record_id"))
            active_by_psr[key] = active_by_psr.get(key, 0) + 1
    for row in tables.get("silver.person_source_record", []):
        psr_id = str(row.get("source_record_id"))
        count = active_by_psr.get(psr_id, 0)
        if count != 1:
            errors.append(f"psr {row.get('source_key')}: {count} active links (expected exactly 1)")
    latest_by_venture: dict[str, int] = {}
    for row in tables.get("gold.venture_score", []):
        if row.get("is_latest") is True:
            key = str(row.get("venture_id"))
            latest_by_venture[key] = latest_by_venture.get(key, 0) + 1
    for row in tables.get("gold.venture", []):
        venture_id = str(row.get("venture_id"))
        if latest_by_venture.get(venture_id, 0) != 1:
            errors.append(f"venture {venture_id}: is_latest score count != 1")
    return errors


def _floats(values: Iterable[Json]) -> list[float]:
    return [float(v) for v in values if isinstance(v, int | float)]


def _embedding_error(table: str, column: str, vector: Json) -> str | None:
    if not isinstance(vector, list) or len(vector) != EMBEDDING_DIM:
        return f"{table}.{column}: not a {EMBEDDING_DIM}-dim vector"
    components = _floats(vector)
    if len(components) != EMBEDDING_DIM:
        return f"{table}.{column}: non-numeric components"
    magnitude = math.sqrt(sum(c * c for c in components))
    if abs(magnitude - 1.0) > _UNIT_NORM_TOLERANCE:
        return f"{table}.{column}: not unit-norm (|v|={magnitude:.6f})"
    return None


def _check_embeddings(tables: Tables) -> list[str]:
    errors: list[str] = []
    holders = [
        ("gold.ideal_candidate", "embedding"),
        ("gold.person_features", "profile_embedding"),
    ]
    for table, column in holders:
        messages = (
            _embedding_error(table, column, row.get(column)) for row in tables.get(table, [])
        )
        errors.extend(message for message in messages if message is not None)
    return errors


def _check_payload_schemas(tables: Tables) -> list[str]:
    errors: list[str] = []
    payloads: list[tuple[str, str, str]] = [
        ("gold.venture_score", "breakdown", "breakdown"),
        ("gold.memo", "sections", "memo"),
        ("gold.ideal_candidate", "profile_json", "ideal"),
        ("gold.interview", "extracted", "interview"),
    ]
    for table, column, schema in payloads:
        for row in tables.get(table, []):
            errors.extend(
                f"{table}.{column}: {message}"
                for message in payload_errors(schema, row.get(column))
            )
    return errors


def _check_bronze_consistency(tables: Tables) -> list[str]:
    errors: list[str] = []
    for row in tables.get("silver.person_source_record", []):
        source = str(row.get("source"))
        source_key = str(row.get("source_key"))
        if row.get("source_record_id") != ids.psr_id(source, source_key):
            errors.append(f"psr {source_key}: source_record_id does not recompute")
        full_name = row.get("full_name")
        if isinstance(full_name, str) and row.get("name_norm") != norm.name_norm(full_name):
            errors.append(f"psr {source_key}: name_norm does not recompute")
        emails = row.get("emails")
        if isinstance(emails, list):
            expected = [n for n in (norm.email_norm(str(e)) for e in emails) if n is not None]
            if row.get("email_norms") != expected:
                errors.append(f"psr {source_key}: email_norms do not recompute")
        affiliation = row.get("affiliation_raw")
        if isinstance(affiliation, str) and row.get("org_norm") != institutions.org_norm(
            affiliation
        ):
            errors.append(f"psr {source_key}: org_norm does not recompute")
    return errors


def _expected_project_id(row: Row) -> str:
    """Recompute a project_id from the row's natural key.

    Hacknation rows have no repo_id; their key is the trailing id= of the
    source_url (the bff-projects endpoint's query parameter).

    Args:
        row: One silver.project fixture row.

    Returns:
        The deterministic id the row must carry.
    """
    repo_id = row.get("repo_id")
    if repo_id is None:
        return ids.hacknation_project_id(str(row.get("source_url")).rpartition("id=")[2])
    return ids.project_id(int(str(repo_id)))


def _check_artifact_ids(tables: Tables) -> list[str]:
    errors: list[str] = []
    errors.extend(
        f"project {row.get('full_name') or row.get('name')}: project_id does not recompute"
        for row in tables.get("silver.project", [])
        if row.get("project_id") != _expected_project_id(row)
    )
    errors.extend(
        f"company {row.get('uid')}: company_id does not recompute"
        for row in tables.get("silver.company", [])
        if row.get("company_id") != ids.company_id(str(row.get("uid")))
    )
    errors.extend(
        f"venture {row.get('name')}: venture_id does not recompute"
        for row in tables.get("gold.venture", [])
        if row.get("venture_id")
        != ids.venture_id(str(row.get("anchor_type")), str(row.get("anchor_id")))
    )
    return errors


def _check_fact_ids(tables: Tables) -> list[str]:
    errors: list[str] = []
    errors.extend(
        f"link {row.get('link_id')}: link_id does not recompute"
        for row in tables.get("silver.person_source_link", [])
        if row.get("link_id")
        != ids.link_id(
            str(row.get("person_id")),
            str(row.get("source_record_id")),
            str(row.get("match_method")),
        )
    )
    errors.extend(
        "contribution: contribution_id does not recompute"
        for row in tables.get("silver.contribution", [])
        if row.get("contribution_id")
        != ids.contribution_id(str(row.get("project_id")), str(row.get("source_record_id")))
    )
    errors.extend(
        "authorship: authorship_id does not recompute"
        for row in tables.get("silver.authorship", [])
        if row.get("authorship_id")
        != ids.authorship_id(str(row.get("publication_id")), str(row.get("source_record_id")))
    )
    errors.extend(
        "officer: officer_id does not recompute"
        for row in tables.get("silver.officer", [])
        if row.get("officer_id")
        != ids.officer_id(
            str(row.get("company_id")),
            str(row.get("source_record_id")),
            str(row.get("role_norm")),
        )
    )
    return errors


def _check_personas(tables: Tables) -> list[str]:
    errors: list[str] = []
    links = tables.get("silver.person_source_link", [])
    psr_source = {
        str(row.get("source_record_id")): str(row.get("source"))
        for row in tables.get("silver.person_source_record", [])
    }
    by_person: dict[str, set[str]] = {}
    for row in links:
        if row.get("status") == "active":
            person = str(row.get("person_id"))
            by_person.setdefault(person, set()).add(psr_source[str(row.get("source_record_id"))])
    lena = "11111111-1111-4111-8111-000000000001"
    if by_person.get(lena) != {"github", "openalex_author", "zefix_officer", "hacknation"}:
        errors.append("persona P1: Lena must link exactly github+openalex+zefix+hacknation")
    retracted = [row for row in links if row.get("status") == "retracted"]
    if len(retracted) != 1:
        errors.append("persona P6: expected exactly one retracted link")
    selin_psr = ids.psr_id("hacknation", "hn-selin-0003")
    selin_cv_urls = [
        row.get("cv_url")
        for row in tables.get("silver.person_source_record", [])
        if row.get("source_record_id") == selin_psr
    ]
    if not any(isinstance(url, str) and url.endswith("hn-selin-0003.pdf") for url in selin_cv_urls):
        errors.append("persona HN: Selin's hacknation PSR must carry her cv_url")
    hn_spines = [
        row
        for row in tables.get("silver.project", [])
        if row.get("source_platform") == "hacknation" and row.get("github_url") is not None
    ]
    if len(hn_spines) != 1:
        errors.append("persona HN: exactly one hacknation project must pitch a github_url (D8)")
    if not tables.get("ops.er_review_queue"):
        errors.append("personas P2/P3: review queue must hold the ambiguous Wei Zhang pair")
    features = {
        str(row.get("person_id")): row.get("profile_embedding")
        for row in tables.get("gold.person_features", [])
    }
    ideal_rows = tables.get("gold.ideal_candidate", [])
    if ideal_rows and features:
        ideal_vec = ideal_rows[0].get("embedding")
        fits = {
            person: cosine(_floats(vector), _floats(ideal_vec))
            for person, vector in features.items()
            if isinstance(vector, list) and isinstance(ideal_vec, list)
        }
        if fits and max(fits, key=lambda person: fits[person]) != lena:
            errors.append("persona P1: Lena must top domain-fit against the robotics ideal")
    return errors


def validate(data_dir: Path = DATA_DIR) -> list[str]:
    """Run every check over the fixture files.

    Args:
        data_dir: The fixtures/data directory.

    Returns:
        All violations found; empty means the contract holds.
    """
    tables = load_tables(data_dir)
    errors: list[str] = []
    for check in (
        _check_fk,
        _check_enums,
        _check_link_invariants,
        _check_embeddings,
        _check_payload_schemas,
        _check_bronze_consistency,
        _check_artifact_ids,
        _check_fact_ids,
        _check_personas,
    ):
        errors.extend(check(tables))
    return errors


def main() -> int:
    """CLI entry point (`poe fixtures-validate`).

    Returns:
        1 when any violation was found.
    """
    errors = validate()
    for error in errors:
        sys.stderr.write(f"FIXTURE VIOLATION: {error}\n")
    if errors:
        return 1
    sys.stdout.write("fixtures valid: all checks passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
