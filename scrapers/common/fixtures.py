"""Fixture replay: route recorded response bodies through httpx.MockTransport.

Replay enters at the transport layer, so fixtures exercise the entire client,
discovery, and normalize stack — the same code path as live runs. An unmatched
request answers 418 (never retried), which raises loudly in the client.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

NO_ROUTE_STATUS: Final[int] = 418

Responder = Callable[[httpx.Request], httpx.Response]


@dataclass(frozen=True, slots=True)
class FixtureRoute:
    """One replay rule: method + URL pattern to a canned response."""

    method: str
    pattern: re.Pattern[str]
    respond: Responder


def json_body(path: Path, status: int = 200) -> Responder:
    """A responder serving a JSON file.

    Args:
        path: The fixture file.
        status: Response status.

    Returns:
        The responder.
    """

    def respond(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            status, content=path.read_bytes(), headers={"Content-Type": "application/json"}
        )

    return respond


def text_body(path: Path, content_type: str, status: int = 200) -> Responder:
    """A responder serving a raw text file (README markdown, Atom XML).

    Args:
        path: The fixture file.
        content_type: Content-Type header value.
        status: Response status.

    Returns:
        The responder.
    """

    def respond(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            status, content=path.read_bytes(), headers={"Content-Type": content_type}
        )

    return respond


def status_only(status: int) -> Responder:
    """A responder answering a bare status (404 readme, 304 unchanged).

    Args:
        status: Response status.

    Returns:
        The responder.
    """

    def respond(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status)

    return respond


def build_mock_transport(routes: Sequence[FixtureRoute]) -> httpx.MockTransport:
    """Assemble the replay transport; first matching route wins.

    Args:
        routes: Ordered replay rules.

    Returns:
        A transport for HttpClient's transport parameter.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        for route in routes:
            if route.method == request.method and route.pattern.search(str(request.url)):
                return route.respond(request)
        return httpx.Response(
            NO_ROUTE_STATUS, text=f"no fixture route: {request.method} {request.url}"
        )

    return httpx.MockTransport(handler)
