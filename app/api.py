"""The /v1 HTTP surface: session-gated proxy over the gold views plus the loop.

Routes mirror the frozen proxy contract: thesis/weights/ideal editors,
ranking, memo/scores/team, outreach, rescore, and the token-authenticated
interview endpoints. VARIANT columns travel as JSON strings (Statement
Execution semantics) so clients JSON.parse them; the static SPA is served
from app/static.
"""

from http import HTTPStatus
from pathlib import Path, PurePosixPath
from typing import Final

from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth import SessionRegistry, bearer_token
from app.deps import AppDeps
from app.interview import (
    ConsentRequiredError,
    ConsumedTokenError,
    ExpiredTokenError,
    ExtractionInvalidError,
    InvalidTokenError,
    SessionBoundError,
)
from app.models import OutreachRequest
from app.outreach import (
    MissingContactError,
    SuppressedPersonError,
    UnknownVentureError,
    send_outreach,
)
from app.rescoring import (
    NoActiveRowError,
    RescoreDeps,
    run_interview_rescore,
)
from app.store import VIEW_RANKED_VENTURES, VIEW_VENTURE_TEAM
from contracts.models import Json
from contracts.validation import payload_errors
from scoring.profile_text import render_ideal_text
from scoring.scripted import OFFLINE_EMBEDDING_MODEL
from scoring.snapshot import get_float
from scrapers.common.jsonutil import as_mapping, as_sink, get_str
from tools.db import canonical_json
from tools.ddl_registry import table_schema
from tools.llm import EMBEDDING_MODEL

STATIC_DIR: Final[Path] = Path(__file__).resolve().parent / "static"


class SpaStaticFiles(StaticFiles):
    """Static files with a single-page-app fallback to index.html.

    The React frontend uses BrowserRouter, so paths like /thesis exist only in
    the client router. Plain StaticFiles 404s them, which breaks refreshes and
    shared links; falling back to index.html lets the router take over.

    Only extension-less paths fall back. A missing /assets/main.js must stay a
    404, or the browser parses the HTML shell as JavaScript and reports a
    syntax error instead of the missing file.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve the file, or index.html when the path is a client-side route.

        Args:
            path: The requested path, relative to the static directory.
            scope: The ASGI connection scope.

        Returns:
            The static response, or the SPA shell for unknown routes.

        Raises:
            HTTPException: On a 404 for an asset path, or any non-404 error.
        """
        is_route = not PurePosixPath(path).suffix
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != HTTPStatus.NOT_FOUND or not is_route:
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == HTTPStatus.NOT_FOUND and is_route:
            return await super().get_response("index.html", scope)
        return response


# Statement-Execution semantics: VARIANT columns cross /v1 as JSON strings.
VARIANT_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "breakdown",
        "sections",
        "evidence",
        "question_plan",
        "transcript",
        "extracted",
        "profile_json",
    }
)
WEIGHT_KEYS: Final[tuple[str, ...]] = (
    "w_individual_experience",
    "w_schools",
    "w_network_ties",
    "w_prior_collaboration",
    "w_problem_realness",
    "w_product_defensibility",
    "w_market",
    "w_traction",
    "w_ideal_match",
)
SESSION_HEADER: Final[str] = "x-interview-session"
_PUBLIC_PREFIXES: Final[tuple[str, ...]] = ("/v1/login", "/v1/interview/", "/v1/optout/")


def render_row(row: dict[str, Json], *, drop: frozenset[str] = frozenset()) -> dict[str, Json]:
    """One row shaped for the wire: VARIANT columns as JSON strings.

    Args:
        row: The stored row.
        drop: Columns to omit (e.g. bulky embeddings).

    Returns:
        The wire-shaped row.
    """
    rendered: dict[str, Json] = {}
    for column, value in row.items():
        if column in drop:
            continue
        stringify = column in VARIANT_COLUMNS and value is not None and not isinstance(value, str)
        rendered[column] = canonical_json(value) if stringify else value
    return rendered


class SessionAuthMiddleware:
    """401s every /v1 request without a valid session, except public routes."""

    def __init__(self, app: ASGIApp, sessions: SessionRegistry) -> None:
        """Wrap the inner ASGI app with the session gate."""
        self._app: Final[ASGIApp] = app
        self._sessions: Final[SessionRegistry] = sessions

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Gate one request.

        Args:
            scope: The ASGI connection scope.
            receive: The ASGI receive channel.
            send: The ASGI send channel.
        """
        if scope["type"] == "http" and self._blocked(scope):
            response = JSONResponse({"error": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)

    def _blocked(self, scope: Scope) -> bool:
        path = str(scope["path"])
        if not path.startswith("/v1/") or path.startswith(_PUBLIC_PREFIXES):
            return False
        token = bearer_token(Headers(scope=scope).get("authorization"))
        return not self._sessions.is_valid(token)


async def _body_object(request: Request) -> dict[str, Json]:
    try:
        raw: object = await request.json()
    except ValueError:
        return {}
    return as_mapping(raw)


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


class ApiHandlers:
    """The /v1 endpoints, closed over one AppDeps composition."""

    def __init__(self, deps: AppDeps) -> None:
        """Bind the composed dependencies."""
        self._deps: Final[AppDeps] = deps

    async def healthz(self, request: Request) -> Response:
        """Liveness probe.

        Args:
            request: The incoming request.

        Returns:
            A static ok body.
        """
        del request
        return JSONResponse({"status": "ok", "fixtures": self._deps.fixtures})

    async def login(self, request: Request) -> Response:
        """Mint a session for the app password.

        Args:
            request: JSON body with 'password'.

        Returns:
            The bearer token, or 401.
        """
        body = await _body_object(request)
        token = self._deps.sessions.login(get_str(body, "password") or "")
        if token is None:
            return _error("invalid password", 401)
        return JSONResponse({"token": token})

    def _rows(self, name: str) -> list[dict[str, Json]]:
        return self._deps.store.rows(name)

    def _active_for_thesis(self, table: str, thesis_id: str) -> dict[str, Json] | None:
        for row in self._rows(table):
            if row.get("thesis_id") == thesis_id and row.get("is_active") is not False:
                return row
        return None

    async def thesis(self, request: Request) -> Response:
        """GET the thesis workspace or POST a thesis upsert.

        Args:
            request: GET, or POST with thesis fields (name required).

        Returns:
            Theses plus their weights and ideal profiles on GET; the stored
            row on POST.
        """
        if request.method == "GET":
            return JSONResponse(
                {
                    "theses": [render_row(row) for row in self._rows("gold.thesis")],
                    "weights": [render_row(row) for row in self._rows("gold.score_weights")],
                    "ideals": [
                        render_row(row, drop=frozenset({"embedding"}))
                        for row in self._rows("gold.ideal_candidate")
                    ],
                }
            )
        return self._thesis_upsert(await _body_object(request))

    def _thesis_upsert(self, body: dict[str, Json]) -> Response:
        name = get_str(body, "name")
        if name is None:
            return _error("thesis 'name' is required", 422)
        columns = set(table_schema("gold.thesis").column_names)
        row: dict[str, Json] = {key: value for key, value in body.items() if key in columns}
        row["thesis_id"] = get_str(body, "thesis_id") or self._deps.id_factory()
        row["name"] = name
        row.setdefault("is_active", True)
        row["updated_at"] = self._deps.clock().isoformat()
        self._deps.store.upsert("gold.thesis", [{k: as_sink(v) for k, v in row.items()}])
        return JSONResponse(render_row(row))

    async def weights_put(self, request: Request) -> Response:
        """Replace the nine weights of a thesis's active weights row.

        Args:
            request: PUT with all nine w_* numeric fields.

        Returns:
            The stored row, or 404/422.
        """
        thesis_id = str(request.path_params["thesis_id"])
        body = await _body_object(request)
        missing = [key for key in WEIGHT_KEYS if get_float(body, key) is None]
        if missing:
            return _error(f"missing or non-numeric weights: {', '.join(missing)}", 422)
        current = self._active_for_thesis("gold.score_weights", thesis_id)
        if current is None:
            return _error(f"no active weights for thesis {thesis_id}", 404)
        updated = dict(current)
        updated.update({key: get_float(body, key) for key in WEIGHT_KEYS})
        updated["updated_at"] = self._deps.clock().isoformat()
        updated["updated_by"] = "app"
        self._deps.store.upsert("gold.score_weights", [{k: as_sink(v) for k, v in updated.items()}])
        return JSONResponse(render_row(updated))

    async def ideal_put(self, request: Request) -> Response:
        """Replace a thesis's active ideal-candidate profile.

        Args:
            request: PUT with the profile_json payload (frozen ideal schema).

        Returns:
            The stored row (embedding omitted), or 404/422.
        """
        thesis_id = str(request.path_params["thesis_id"])
        payload = await _body_object(request)
        errors = payload_errors("ideal", payload)
        if errors:
            return JSONResponse({"errors": errors}, status_code=422)
        current = self._active_for_thesis("gold.ideal_candidate", thesis_id)
        if current is None:
            return _error(f"no active ideal profile for thesis {thesis_id}", 404)
        profile_text = render_ideal_text(payload)
        updated = dict(current)
        updated["profile_json"] = payload
        updated["profile_text"] = profile_text
        updated["embedding"] = list(self._deps.llm.embed(profile_text))
        updated["embedding_model"] = (
            OFFLINE_EMBEDDING_MODEL if self._deps.fixtures else EMBEDDING_MODEL
        )
        version = updated.get("version")
        updated["version"] = (version + 1) if isinstance(version, int) else 1
        updated["updated_at"] = self._deps.clock().isoformat()
        updated["updated_by"] = "app"
        self._deps.store.upsert(
            "gold.ideal_candidate", [{k: as_sink(v) for k, v in updated.items()}]
        )
        return JSONResponse(render_row(updated, drop=frozenset({"embedding"})))

    def _default_thesis_id(self) -> str | None:
        for row in self._rows("gold.thesis"):
            if row.get("is_active") is not False:
                return get_str(row, "thesis_id")
        return None

    async def ranking(self, request: Request) -> Response:
        """The ranked candidate pool for one thesis.

        Args:
            request: GET with optional thesis_id query parameter.

        Returns:
            Pool-included ventures ordered by final score, plus the active
            weights row the client sliders start from.
        """
        thesis_id = request.query_params.get("thesis_id") or self._default_thesis_id()
        if thesis_id is None:
            return _error("no thesis found", 404)
        included = {
            get_str(row, "venture_id")
            for row in self._rows("gold.candidate_pool")
            if row.get("thesis_id") == thesis_id and row.get("included") is True
        }
        ventures = [
            render_row(row)
            for row in self._rows(VIEW_RANKED_VENTURES)
            if get_str(row, "venture_id") in included
        ]
        ventures.sort(key=lambda row: get_float(row, "final_score") or -1.0, reverse=True)
        weights = self._active_for_thesis("gold.score_weights", thesis_id)
        return JSONResponse(
            {
                "thesis_id": thesis_id,
                "ventures": ventures,
                "weights": render_row(weights) if weights is not None else None,
            }
        )

    async def memo(self, request: Request) -> Response:
        """The latest memo of one venture.

        Args:
            request: GET with the venture_id path parameter.

        Returns:
            The memo row (sections as a JSON string), or 404.
        """
        venture_id = str(request.path_params["venture_id"])
        for row in self._rows("gold.memo"):
            if row.get("venture_id") == venture_id and row.get("is_latest") is True:
                return JSONResponse(render_row(row))
        return _error(f"no memo for venture {venture_id}", 404)

    async def scores(self, request: Request) -> Response:
        """The score history of one venture, latest first.

        Args:
            request: GET with the venture_id path parameter.

        Returns:
            The venture_score rows (breakdown as a JSON string).
        """
        venture_id = str(request.path_params["venture_id"])
        rows = [
            render_row(row)
            for row in self._rows("gold.venture_score")
            if row.get("venture_id") == venture_id
        ]
        rows.sort(key=lambda row: get_str(row, "scored_at") or "", reverse=True)
        return JSONResponse({"scores": rows})

    async def team(self, request: Request) -> Response:
        """The resolved team of one venture (gold.v_venture_team contract).

        Args:
            request: GET with the venture_id path parameter.

        Returns:
            The team rows (member evidence as a JSON string).
        """
        venture_id = str(request.path_params["venture_id"])
        rows = [
            render_row(row)
            for row in self._rows(VIEW_VENTURE_TEAM)
            if row.get("venture_id") == venture_id
        ]
        return JSONResponse({"team": rows})

    async def outreach_post(self, request: Request) -> Response:
        """Mint a token and send the compliant outreach email for a venture.

        Args:
            request: POST with optional thesis_id in the body.

        Returns:
            The outreach identifiers plus the interview URL (fixtures demo
            has no inbox), or a typed error.
        """
        venture_id = str(request.path_params["venture_id"])
        body = await _body_object(request)
        try:
            result = send_outreach(
                self._deps.store,
                self._deps.mailer,
                OutreachRequest(
                    venture_id=venture_id,
                    thesis_id=get_str(body, "thesis_id") or self._default_thesis_id(),
                    base_url=self._deps.base_url,
                    actor="app",
                ),
                clock=self._deps.clock,
                id_factory=self._deps.id_factory,
            )
        except UnknownVentureError:
            return _error(f"no venture {venture_id}", 404)
        except MissingContactError:
            return _error("no contactable team member", 422)
        except SuppressedPersonError:
            return _error("person is suppressed (opt-out or erasure)", 409)
        return JSONResponse(
            {
                "outreach_id": result.outreach_id,
                "status": result.status,
                "to_email": result.to_email,
                "interview_url": result.interview_url,
            }
        )

    async def outreach_list(self, request: Request) -> Response:
        """Every outreach row (optionally one thesis), for the status board.

        Args:
            request: GET with optional thesis_id query parameter.

        Returns:
            The outreach rows (question_plan as a JSON string).
        """
        thesis_id = request.query_params.get("thesis_id")
        rows = [
            render_row(row)
            for row in self._rows("gold.outreach")
            if thesis_id is None or row.get("thesis_id") == thesis_id
        ]
        rows.sort(key=lambda row: get_str(row, "last_event_at") or "", reverse=True)
        return JSONResponse({"outreach": rows})

    async def rescore_post(self, request: Request) -> Response:
        """Manually re-run the interview-triggered rescore for a venture.

        Args:
            request: POST with the venture_id path parameter.

        Returns:
            The rescore outcome summary, or 409 without a completed interview.
        """
        venture_id = str(request.path_params["venture_id"])
        interview = self._latest_interview(venture_id)
        if interview is None:
            return _error("no completed interview to rescore from", 409)
        deps = RescoreDeps(
            llm=self._deps.llm,
            clock=self._deps.clock,
            id_factory=self._deps.id_factory,
            offline=self._deps.fixtures,
        )
        try:
            outcome = run_interview_rescore(self._deps.store, deps, interview)
        except NoActiveRowError as error:
            return _error(str(error), 409)
        score_row = outcome.score_rows[0] if outcome.score_rows else None
        final = score_row.get("final_score") if score_row is not None else None
        return JSONResponse(
            {
                "status": outcome.status,
                "score_id": str(score_row.get("score_id")) if score_row is not None else None,
                "final_score": float(final)
                if isinstance(final, int | float) and not isinstance(final, bool)
                else None,
            }
        )

    def _latest_interview(self, venture_id: str) -> dict[str, Json] | None:
        candidates = [
            row
            for row in self._rows("gold.interview")
            if row.get("venture_id") == venture_id and row.get("completed_at") is not None
        ]
        candidates.sort(key=lambda row: get_str(row, "completed_at") or "", reverse=True)
        return candidates[0] if candidates else None

    def _interview_session(self, request: Request) -> str | None:
        return request.headers.get(SESSION_HEADER)

    async def interview_get(self, request: Request) -> Response:
        """Open the interview: validate the token and return the consent screen.

        Args:
            request: GET with the token path parameter and session header.

        Returns:
            The consent-screen payload, or a typed token error.
        """
        session = self._interview_session(request)
        if session is None:
            return _error(f"missing {SESSION_HEADER} header", 400)
        token = str(request.path_params["token"])
        try:
            return JSONResponse(self._deps.engine.open(token, session))
        except (InvalidTokenError, ExpiredTokenError, ConsumedTokenError, SessionBoundError) as e:
            return self._interview_error(e)

    async def interview_message(self, request: Request) -> Response:
        """One founder chat turn (the first one answers the consent prompt).

        Args:
            request: POST with 'text' in the body plus the session header.

        Returns:
            The assistant reply, or a typed token error.
        """
        session = self._interview_session(request)
        if session is None:
            return _error(f"missing {SESSION_HEADER} header", 400)
        token = str(request.path_params["token"])
        body = await _body_object(request)
        text = get_str(body, "text")
        if text is None or not text.strip():
            return _error("'text' is required", 422)
        try:
            return JSONResponse(self._deps.engine.message(token, session, text))
        except (InvalidTokenError, ExpiredTokenError, ConsumedTokenError, SessionBoundError) as e:
            return self._interview_error(e)

    async def interview_complete(self, request: Request) -> Response:
        """Finish the interview, persist it, and trigger the rescore.

        Args:
            request: POST with the token path parameter and session header.

        Returns:
            The completion summary, or a typed error.
        """
        session = self._interview_session(request)
        if session is None:
            return _error(f"missing {SESSION_HEADER} header", 400)
        token = str(request.path_params["token"])
        try:
            return JSONResponse(self._deps.engine.complete(token, session))
        except ConsentRequiredError as error:
            return _error(str(error), 403)
        except ExtractionInvalidError as error:
            return _error(str(error), 422)
        except (InvalidTokenError, ExpiredTokenError, ConsumedTokenError, SessionBoundError) as e:
            return self._interview_error(e)

    def _interview_error(self, error: Exception) -> JSONResponse:
        status = 404 if isinstance(error, InvalidTokenError) else 409
        if isinstance(error, ExpiredTokenError | ConsumedTokenError):
            status = 410
        return _error(str(error), status)

    async def opt_out(self, request: Request) -> Response:
        """One-click opt-out from the email link.

        Args:
            request: GET with the token path parameter.

        Returns:
            A plain-text confirmation (200 even for unknown tokens, so the
            link never leaks whether an outreach exists).
        """
        token = str(request.path_params["token"])
        self._deps.engine.opt_out(token)
        return PlainTextResponse(
            "You have been opted out. We will not contact you again, and you "
            "can request full erasure by replying to the original email."
        )


def create_app(deps: AppDeps) -> Starlette:
    """Assemble the ASGI app: /v1 routes, session gate, static SPA.

    Args:
        deps: The composed dependencies.

    Returns:
        The Starlette application.
    """
    handlers = ApiHandlers(deps)
    routes = [
        Route("/healthz", handlers.healthz, methods=["GET"]),
        Route("/v1/login", handlers.login, methods=["POST"]),
        Route("/v1/thesis", handlers.thesis, methods=["GET", "POST"]),
        Route("/v1/thesis/{thesis_id}/weights", handlers.weights_put, methods=["PUT"]),
        Route("/v1/thesis/{thesis_id}/ideal-candidate", handlers.ideal_put, methods=["PUT"]),
        Route("/v1/ranking", handlers.ranking, methods=["GET"]),
        Route("/v1/venture/{venture_id}/memo", handlers.memo, methods=["GET"]),
        Route("/v1/venture/{venture_id}/scores", handlers.scores, methods=["GET"]),
        Route("/v1/venture/{venture_id}/team", handlers.team, methods=["GET"]),
        Route("/v1/venture/{venture_id}/outreach", handlers.outreach_post, methods=["POST"]),
        Route("/v1/venture/{venture_id}/rescore", handlers.rescore_post, methods=["POST"]),
        Route("/v1/outreach", handlers.outreach_list, methods=["GET"]),
        Route("/v1/interview/{token}", handlers.interview_get, methods=["GET"]),
        Route("/v1/interview/{token}/message", handlers.interview_message, methods=["POST"]),
        Route("/v1/interview/{token}/complete", handlers.interview_complete, methods=["POST"]),
        Route("/v1/optout/{token}", handlers.opt_out, methods=["GET"]),
        Mount("/", app=SpaStaticFiles(directory=STATIC_DIR, html=True), name="static"),
    ]
    middleware = [Middleware(SessionAuthMiddleware, sessions=deps.sessions)]
    return Starlette(routes=routes, middleware=middleware)
