"""The interview loop: token binding, consent-first transcript, skip, expiry,
completion sync into gold.interview plus the targeted rescore."""

import hashlib
from typing import Final

from app.deps import AppDeps
from app.interview import CONSENT_PROMPT
from fixtures import build
from scrapers.common.jsonutil import get_str
from tests.app.conftest import AppClient, dict_items, mint_interview_token

DEVICE_A: Final[dict[str, str]] = {"X-Interview-Session": "device-a"}
DEVICE_B: Final[dict[str, str]] = {"X-Interview-Session": "device-b"}
CONSENT_TEXT: Final[str] = "Yes, I consent to this interview and to my answers being stored."


def test_open_requires_a_session_header(client: AppClient, auth: dict[str, str]) -> None:
    token = mint_interview_token(client, auth, build.GRASP_VENTURE)
    assert client.get(f"/v1/interview/{token}").status_code == 400


def test_unknown_token_is_rejected(client: AppClient) -> None:
    assert client.get("/v1/interview/deadbeef", headers=DEVICE_A).status_code == 404


def test_open_binds_the_first_session_and_blocks_a_second_device(
    client: AppClient, auth: dict[str, str]
) -> None:
    token = mint_interview_token(client, auth, build.GRASP_VENTURE)
    opened = client.get(f"/v1/interview/{token}", headers=DEVICE_A)
    assert opened.status_code == 200
    assert opened.body["consented"] is False
    assert opened.body["questions_total"] == 2
    assert opened.body["consent_prompt"] == CONSENT_PROMPT
    # Same device may reopen; a second device is rejected.
    assert client.get(f"/v1/interview/{token}", headers=DEVICE_A).status_code == 200
    assert client.get(f"/v1/interview/{token}", headers=DEVICE_B).status_code == 409


def test_expired_token_is_rejected(deps: AppDeps, client: AppClient, auth: dict[str, str]) -> None:
    del auth
    deps.store.upsert(
        "gold.outreach",
        [
            {
                "outreach_id": "test-expired-1",
                "venture_id": build.GRASP_VENTURE,
                "person_id": build.LENA,
                "channel": "email",
                "status": "sent",
                "token_hash": hashlib.sha256(b"expired-token").hexdigest(),
                "token_expires_at": "2020-01-01T00:00:00+00:00",
                "updated_at": "2020-01-01T00:00:00+00:00",
            }
        ],
    )
    response = client.get("/v1/interview/expired-token", headers=DEVICE_A)
    assert response.status_code == 410
    assert "expired" in (get_str(response.body, "error") or "")


def test_decline_flips_the_outreach_to_declined(
    deps: AppDeps, client: AppClient, auth: dict[str, str]
) -> None:
    token = mint_interview_token(client, auth, build.GRASP_VENTURE)
    response = client.post(
        f"/v1/interview/{token}/message",
        payload={"text": "No, I do not consent."},
        headers=DEVICE_A,
    )
    assert response.status_code == 200
    assert response.body["declined"] is True
    statuses = {get_str(row, "status") for row in deps.store.rows("gold.outreach")}
    assert "declined" in statuses


def test_complete_before_consent_is_forbidden(client: AppClient, auth: dict[str, str]) -> None:
    token = mint_interview_token(client, auth, build.GRASP_VENTURE)
    assert client.get(f"/v1/interview/{token}", headers=DEVICE_A).status_code == 200
    assert client.post(f"/v1/interview/{token}/complete", headers=DEVICE_A).status_code == 403


def test_full_loop_records_consent_first_and_triggers_the_rescore(
    deps: AppDeps, client: AppClient, auth: dict[str, str]
) -> None:
    token = mint_interview_token(client, auth, build.GRASP_VENTURE)
    scores_before = client.get(f"/v1/venture/{build.GRASP_VENTURE}/scores", headers=auth).items(
        "scores"
    )

    consent = client.post(
        f"/v1/interview/{token}/message", payload={"text": CONSENT_TEXT}, headers=DEVICE_A
    ).body
    assert consent["declined"] is False
    assert "Do you have paying pilots" in (get_str(consent, "assistant") or "")
    answer = client.post(
        f"/v1/interview/{token}/message",
        payload={"text": "Three paid pilots with logistics companies."},
        headers=DEVICE_A,
    ).body
    assert answer["done"] is False
    skipped = client.post(
        f"/v1/interview/{token}/message", payload={"text": "skip"}, headers=DEVICE_A
    ).body
    assert skipped["done"] is True

    completed = client.post(f"/v1/interview/{token}/complete", headers=DEVICE_A)
    assert completed.status_code == 200
    summary = completed.body
    assert summary["rescore_status"] == "ok"
    assert summary["rescore_score_id"]

    # Consent is the first transcript content, recorded verbatim.
    interviews = [
        row
        for row in deps.store.rows("gold.interview")
        if row.get("interview_id") == summary["interview_id"]
    ]
    assert len(interviews) == 1
    transcript = dict_items(interviews[0].get("transcript"))
    assert transcript[0].get("role") == "assistant"
    assert transcript[0].get("text") == CONSENT_PROMPT
    assert transcript[1].get("role") == "founder"
    assert transcript[1].get("text") == CONSENT_TEXT
    assert interviews[0]["consent_confirmed"] is True
    assert interviews[0]["rescore_score_id"] == summary["rescore_score_id"]

    # The outreach walked the state machine and is now consumed.
    outreach = next(
        row
        for row in deps.store.rows("gold.outreach")
        if row.get("outreach_id") == interviews[0]["outreach_id"]
    )
    assert outreach["status"] == "interviewed"
    history_states = [entry.get("state") for entry in dict_items(outreach.get("history"))]
    assert history_states == ["draft", "sent", "consented", "interview_started", "interviewed"]
    assert outreach["consent_at"] is not None
    assert client.get(f"/v1/interview/{token}", headers=DEVICE_A).status_code == 410

    # A new latest score row exists, produced through ingest_interview.
    scores_after = client.get(f"/v1/venture/{build.GRASP_VENTURE}/scores", headers=auth).items(
        "scores"
    )
    assert len(scores_after) == len(scores_before) + 1
    assert scores_after[0]["score_id"] == summary["rescore_score_id"]
    assert scores_after[0]["is_latest"] is True
    run_rows = deps.store.rows("gold.score_run")
    assert [get_str(row, "status") for row in run_rows] == ["ok"]


def test_manual_rescore_endpoint_is_idempotent_after_the_interview(
    client: AppClient, auth: dict[str, str]
) -> None:
    token = mint_interview_token(client, auth, build.GRASP_VENTURE)
    client.post(f"/v1/interview/{token}/message", payload={"text": CONSENT_TEXT}, headers=DEVICE_A)
    client.post(f"/v1/interview/{token}/message", payload={"text": "skip"}, headers=DEVICE_A)
    client.post(f"/v1/interview/{token}/message", payload={"text": "skip"}, headers=DEVICE_A)
    assert client.post(f"/v1/interview/{token}/complete", headers=DEVICE_A).status_code == 200
    rerun = client.post(f"/v1/venture/{build.GRASP_VENTURE}/rescore", payload={}, headers=auth).body
    assert rerun["status"] == "skipped_duplicate"


def test_opt_out_link_flips_the_row_without_auth(
    deps: AppDeps, client: AppClient, auth: dict[str, str]
) -> None:
    token = mint_interview_token(client, auth, build.GRASP_VENTURE)
    response = client.get(f"/v1/optout/{token}")
    assert response.status_code == 200
    assert "opted out" in response.text
    statuses = {get_str(row, "status") for row in deps.store.rows("gold.outreach")}
    assert "opted_out" in statuses
    # The token is dead afterwards.
    assert client.get(f"/v1/interview/{token}", headers=DEVICE_A).status_code == 410
