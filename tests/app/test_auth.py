"""The session gate: 401 without a token, login mints one, public routes stay open."""

from tests.app.conftest import AppClient


def test_v1_routes_are_gated_without_session(client: AppClient) -> None:
    assert client.get("/v1/ranking").status_code == 401
    assert client.get("/v1/thesis").status_code == 401
    assert client.get("/v1/outreach").status_code == 401


def test_wrong_password_is_rejected(client: AppClient) -> None:
    assert client.post("/v1/login", payload={"password": "wrong"}).status_code == 401


def test_login_mints_a_working_bearer_token(client: AppClient) -> None:
    token = client.post("/v1/login", payload={"password": "demo"}).body["token"]
    assert isinstance(token, str)
    response = client.get("/v1/ranking", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_garbage_bearer_token_is_rejected(client: AppClient) -> None:
    response = client.get("/v1/ranking", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_healthz_is_public(client: AppClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.body == {"status": "ok", "fixtures": True}
