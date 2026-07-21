"""Outreach: token minting (hash stored, not the token), compliant email,
state transitions with history, and the suppression gate."""

import hashlib

from app.deps import AppDeps
from app.outreach import RecordingMailer
from contracts.models import Json
from fixtures import build
from scrapers.common.jsonutil import as_mapping, get_list, get_str
from tests.app.conftest import AppClient, dict_items


def _new_outreach_row(deps: AppDeps, outreach_id: Json) -> dict[str, Json]:
    rows = [
        row for row in deps.store.rows("gold.outreach") if row.get("outreach_id") == outreach_id
    ]
    assert len(rows) == 1
    return dict(rows[0])


def _recording(deps: AppDeps) -> RecordingMailer:
    mailer = deps.mailer
    assert isinstance(mailer, RecordingMailer)
    return mailer


def test_outreach_post_mints_token_and_sends_compliant_mail(
    deps: AppDeps, client: AppClient, auth: dict[str, str]
) -> None:
    response = client.post(f"/v1/venture/{build.GRASP_VENTURE}/outreach", payload={}, headers=auth)
    assert response.status_code == 200
    body = response.body
    assert body["status"] == "sent"
    assert body["to_email"] == "lena.fischer@ethz.ch"
    interview_url = get_str(body, "interview_url") or ""
    token = interview_url.rsplit("/", 1)[-1]

    row = _new_outreach_row(deps, body["outreach_id"])
    stored_hash = row["token_hash"]
    assert stored_hash != token  # never the raw token
    assert stored_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert row["status"] == "sent"
    assert [entry.get("state") for entry in dict_items(row.get("history"))] == ["draft", "sent"]

    mailer = _recording(deps)
    assert len(mailer.sent) == 1
    mail = mailer.sent[0]
    assert mail.to_email == "lena.fischer@ethz.ch"
    # Compliance: sender identity, why contacted + data source, opt-out.
    assert "Venture Hunt" in mail.body
    assert "We came across your GitHub profile @lenafischer" in mail.body
    assert "public data only" in mail.body
    assert "/v1/optout/" in mail.body
    assert interview_url in mail.body


def test_question_plan_comes_from_the_gap_rows(
    deps: AppDeps, client: AppClient, auth: dict[str, str]
) -> None:
    body = client.post(f"/v1/venture/{build.GRASP_VENTURE}/outreach", payload={}, headers=auth).body
    row = _new_outreach_row(deps, body["outreach_id"])
    plan = as_mapping(row.get("question_plan"))
    assert get_list(plan, "questions") == [
        "Do you have paying pilots or revenue today?",
        "Which customer segment do you serve first, and how large is it?",
    ]


def test_erasure_suppression_blocks_the_send(
    deps: AppDeps, client: AppClient, auth: dict[str, str]
) -> None:
    # Suppress Lena's active github identity (source_key 501001).
    deps.store.upsert(
        "ops.erasure_suppression",
        [
            {
                "source": "github",
                "source_key_hash": hashlib.sha256(b"501001").hexdigest(),
                "created_at": "2026-07-16T00:00:00+00:00",
            }
        ],
    )
    response = client.post(f"/v1/venture/{build.GRASP_VENTURE}/outreach", payload={}, headers=auth)
    assert response.status_code == 409
    assert "suppressed" in (get_str(response.body, "error") or "")
    assert _recording(deps).sent == []


def test_opted_out_person_blocks_the_send(
    deps: AppDeps, client: AppClient, auth: dict[str, str]
) -> None:
    deps.store.upsert(
        "gold.outreach",
        [
            {
                "outreach_id": "test-optout-1",
                "venture_id": build.GRASP_VENTURE,
                "person_id": build.LENA,
                "channel": "email",
                "status": "opted_out",
                "updated_at": "2026-07-16T00:00:00+00:00",
            }
        ],
    )
    response = client.post(f"/v1/venture/{build.GRASP_VENTURE}/outreach", payload={}, headers=auth)
    assert response.status_code == 409


def test_outreach_post_404s_for_an_unknown_venture(client: AppClient, auth: dict[str, str]) -> None:
    assert client.post("/v1/venture/nope/outreach", payload={}, headers=auth).status_code == 404


def test_outreach_board_lists_every_row(client: AppClient, auth: dict[str, str]) -> None:
    client.post(f"/v1/venture/{build.GRASP_VENTURE}/outreach", payload={}, headers=auth)
    rows = client.get("/v1/outreach", headers=auth).items("outreach")
    statuses = {get_str(row, "status") for row in rows}
    assert statuses == {"sent", "consented"}  # fresh send + fixture row
