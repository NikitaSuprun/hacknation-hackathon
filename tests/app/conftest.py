# Copyright (c) 2026 Maschmeyer's Chosen Portfolio. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Shared WS-F fixtures: one fixtures-mode app per test, driven in-process.

starlette 1.3 types TestClient against the optional httpx2 package, which this
project does not ship — so AppClient below is the one typed facade over it
(the pyright ignores are confined to _call)."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Protocol, cast

import pytest
from starlette.testclient import TestClient

from app.api import create_app
from app.deps import AppDeps, build_fixture_deps
from contracts.models import Json
from scrapers.common.jsonutil import as_list, as_mapping

BASE_URL = "http://testserver"
PASSWORD = "demo"


def dict_items(value: Json) -> list[dict[str, Json]]:
    """Narrow a JSON array of objects (empty for anything else).

    Args:
        value: Any decoded JSON value.

    Returns:
        The list of object items.
    """
    return [as_mapping(item) for item in as_list(value)]


@dataclass(frozen=True, slots=True)
class ApiResponse:
    """One typed API reply: status, decoded object body, raw text."""

    status_code: int
    body: dict[str, Json]
    text: str

    def items(self, key: str) -> list[dict[str, Json]]:
        """The body field as a list of JSON objects.

        Args:
            key: The top-level body field.

        Returns:
            The narrowed list.
        """
        return dict_items(self.body.get(key))


class _ResponseLike(Protocol):
    """The two response members the tests consume."""

    status_code: int
    text: str


class AppClient:
    """Typed facade over starlette's TestClient for the /v1 surface."""

    def __init__(self, deps: AppDeps) -> None:
        """Build the ASGI app from the deps and wrap a test client."""
        self._client: Final[TestClient] = TestClient(create_app(deps))

    def _call(
        self,
        method: str,
        path: str,
        payload: Json | None,
        headers: Mapping[str, str] | None,
    ) -> ApiResponse:
        raw: object = self._client.request(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType] - TestClient is typed against the absent httpx2
            method, path, json=payload, headers=dict(headers or {})
        )
        response = cast("_ResponseLike", raw)
        try:
            decoded: object = json.loads(response.text)
        except ValueError:
            decoded = None
        return ApiResponse(
            status_code=response.status_code, body=as_mapping(decoded), text=response.text
        )

    def get(self, path: str, *, headers: Mapping[str, str] | None = None) -> ApiResponse:
        """GET a path.

        Args:
            path: The request path.
            headers: Extra headers.

        Returns:
            The typed response.
        """
        return self._call("GET", path, None, headers)

    def post(
        self,
        path: str,
        *,
        payload: Json | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ApiResponse:
        """POST a JSON payload.

        Args:
            path: The request path.
            payload: The JSON body.
            headers: Extra headers.

        Returns:
            The typed response.
        """
        return self._call("POST", path, payload, headers)

    def put(
        self,
        path: str,
        *,
        payload: Json | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ApiResponse:
        """PUT a JSON payload.

        Args:
            path: The request path.
            payload: The JSON body.
            headers: Extra headers.

        Returns:
            The typed response.
        """
        return self._call("PUT", path, payload, headers)


@pytest.fixture
def deps() -> AppDeps:
    """A fresh zero-credential composition (fixture store overlay starts empty)."""
    return build_fixture_deps(base_url=BASE_URL)


@pytest.fixture
def client(deps: AppDeps) -> AppClient:
    """A typed test client over the composed ASGI app."""
    return AppClient(deps)


@pytest.fixture
def auth(client: AppClient) -> dict[str, str]:
    """Authorization headers for a freshly minted VC session."""
    response = client.post("/v1/login", payload={"password": PASSWORD})
    assert response.status_code == 200
    token = response.body.get("token")
    assert isinstance(token, str)
    return {"Authorization": f"Bearer {token}"}


def mint_interview_token(client: AppClient, auth_headers: dict[str, str], venture_id: str) -> str:
    """Send an outreach for the venture and return the raw interview token.

    Args:
        client: The test client.
        auth_headers: A valid VC session.
        venture_id: The venture to reach out for.

    Returns:
        The raw token from the returned interview URL.
    """
    response = client.post(f"/v1/venture/{venture_id}/outreach", payload={}, headers=auth_headers)
    assert response.status_code == 200
    url = response.body.get("interview_url")
    assert isinstance(url, str)
    return url.rsplit("/", 1)[-1]
