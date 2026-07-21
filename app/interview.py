"""The consent-gated founder interview: token auth, chat loop, completion sync.

Founders authenticate by the emailed single-use token (sha256 matched against
gold.outreach.token_hash, unexpired, bound to the first session that opens
it). Consent is recorded verbatim as the first transcript entries before any
substantive question; completion writes gold.interview, flips the outreach to
interviewed, consumes the token, and triggers the targeted rescore.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.models import OutreachTransition, TokenClaims
from app.outreach import token_hash, transition_outreach
from app.store import DataStore
from contracts.interfaces import LLMClient
from contracts.models import Json, SinkValue
from contracts.validation import bundled_schema, payload_errors
from scoring.rescore import RescoreOutcome
from scoring.snapshot import as_utc
from scrapers.common.jsonutil import as_mapping, as_sink, get_list, get_map, get_str

ROLE_ASSISTANT: Final[str] = "assistant"
ROLE_FOUNDER: Final[str] = "founder"
SKIP_COMMAND: Final[str] = "skip"
CONSENT_PROMPT: Final[str] = (
    "Before we begin: do you consent to this short interview and to your "
    "answers being stored and used to evaluate your venture? You can decline, "
    "skip any question, or request erasure later."
)
WRAP_UP_TEXT: Final[str] = "That covers everything we hoped to ask. Press Complete to finish."
DECLINE_ACK: Final[str] = (
    "Understood — nothing has been recorded beyond your answer, and we will "
    "not contact you again about this interview."
)
_AFFIRMATIVE_PREFIXES: Final[tuple[str, ...]] = ("yes", "i consent", "i agree", "ok", "sure")
_OPEN_STATUSES: Final[frozenset[str]] = frozenset(
    {"sent", "replied", "consented", "interview_scheduled", "interview_started"}
)

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]
type Rescorer = Callable[[Mapping[str, Json]], RescoreOutcome]


class InvalidTokenError(LookupError):
    """The token matches no outreach row."""

    def __init__(self) -> None:
        """Fixed message; the token itself is never echoed."""
        super().__init__("unknown interview token")


class ExpiredTokenError(PermissionError):
    """The token's validity window has passed."""

    def __init__(self) -> None:
        """Fixed message."""
        super().__init__("this interview link has expired")


class ConsumedTokenError(PermissionError):
    """The outreach is in a state that admits no (further) interview."""

    def __init__(self, status: str) -> None:
        """Name the blocking status."""
        super().__init__(f"this interview link is no longer usable (status: {status})")


class SessionBoundError(PermissionError):
    """The token is already bound to a different session or device."""

    def __init__(self) -> None:
        """Fixed message."""
        super().__init__("this interview is already open on another device")


class ConsentRequiredError(PermissionError):
    """A substantive action was attempted before consent."""

    def __init__(self) -> None:
        """Fixed message."""
        super().__init__("consent has not been given")


class ExtractionInvalidError(ValueError):
    """The extracted interview payload violates the frozen schema."""

    def __init__(self, errors: list[str]) -> None:
        """Carry every violation in the message."""
        super().__init__("; ".join(errors) or "no structured payload extracted")


class _ActiveState:
    """Mutable per-token interview progress (single-process demo scope)."""

    def __init__(self, session: str) -> None:
        """Bind the first session that opened the token."""
        self.session: str = session
        self.transcript: list[Json] = []
        self.question_index: int = 0
        self.consent_confirmed: bool = False
        self.started_at: datetime | None = None


def _entry(role: str, text: str, now: datetime) -> Json:
    return {"role": role, "text": text, "at": now.isoformat()}


def _is_affirmative(text: str) -> bool:
    return text.strip().lower().startswith(_AFFIRMATIVE_PREFIXES)


@dataclass(frozen=True, slots=True)
class EngineDeps:
    """The seams one InterviewEngine runs against."""

    store: DataStore
    llm: LLMClient
    rescore: Rescorer
    clock: Clock
    id_factory: IdFactory
    model_version: str


class InterviewEngine:
    """Drives the founder-facing interview loop over the data store."""

    def __init__(self, deps: EngineDeps) -> None:
        """Bind the seams; per-token progress starts empty."""
        self._store: Final[DataStore] = deps.store
        self._llm: Final[LLMClient] = deps.llm
        self._rescore: Final[Rescorer] = deps.rescore
        self._clock: Final[Clock] = deps.clock
        self._id_factory: Final[IdFactory] = deps.id_factory
        self._model_version: Final[str] = deps.model_version
        self._active: Final[dict[str, _ActiveState]] = {}

    def _outreach_row(self, token: str) -> dict[str, Json]:
        hashed = token_hash(token)
        for row in self._store.rows("gold.outreach"):
            if row.get("token_hash") == hashed:
                return row
        raise InvalidTokenError

    def _claims(self, token: str) -> tuple[TokenClaims, dict[str, Json]]:
        row = self._outreach_row(token)
        status = get_str(row, "status") or "draft"
        if status not in _OPEN_STATUSES:
            raise ConsumedTokenError(status)
        expires_at = as_utc(get_str(row, "token_expires_at"))
        if expires_at is not None and self._clock() > expires_at:
            raise ExpiredTokenError
        questions = tuple(
            text
            for item in get_list(get_map(row, "question_plan"), "questions")
            if isinstance(text := item, str)
        )
        claims = TokenClaims(
            outreach_id=get_str(row, "outreach_id") or "",
            venture_id=get_str(row, "venture_id") or "",
            person_id=get_str(row, "person_id") or "",
            thesis_id=get_str(row, "thesis_id"),
            status=status,
            expires_at=expires_at,
            questions=questions,
        )
        return claims, row

    def _state(self, claims: TokenClaims, session: str) -> _ActiveState:
        state = self._active.get(claims.outreach_id)
        if state is None:
            state = _ActiveState(session)
            self._active[claims.outreach_id] = state
        if state.session != session:
            raise SessionBoundError
        return state

    def _venture_name(self, venture_id: str) -> str:
        for row in self._store.rows("gold.venture"):
            if row.get("venture_id") == venture_id:
                return get_str(row, "name") or venture_id
        return venture_id

    def open(self, token: str, session: str) -> dict[str, Json]:
        """Validate the token, bind the session, and return the consent screen.

        Args:
            token: The raw emailed token.
            session: The caller's device session id (first one wins).

        Returns:
            Consent-screen data plus any transcript so far.
        """
        claims, row = self._claims(token)
        state = self._state(claims, session)
        return {
            "venture_name": self._venture_name(claims.venture_id),
            "fund_name": "Venture Hunt",
            "why_contacted": get_str(row, "body"),
            "consent_prompt": CONSENT_PROMPT,
            "consented": state.consent_confirmed,
            "questions_total": len(claims.questions),
            "transcript": list(state.transcript),
        }

    def _record_consent(
        self, claims: TokenClaims, state: _ActiveState, text: str, row: dict[str, Json]
    ) -> dict[str, Json]:
        now = self._clock()
        state.transcript.append(_entry(ROLE_ASSISTANT, CONSENT_PROMPT, now))
        state.transcript.append(_entry(ROLE_FOUNDER, text, now))
        if not _is_affirmative(text):
            step = OutreachTransition(
                status="declined", actor=claims.person_id, now=now, consent_at=None
            )
            transition_outreach(self._store, row, step)
            return {"assistant": DECLINE_ACK, "declined": True, "done": True}
        state.consent_confirmed = True
        state.started_at = now
        updated = transition_outreach(
            self._store,
            row,
            OutreachTransition(status="consented", actor=claims.person_id, now=now, consent_at=now),
        )
        transition_outreach(
            self._store,
            updated,
            OutreachTransition(
                status="interview_started", actor=claims.person_id, now=now, consent_at=None
            ),
        )
        first = claims.questions[0] if claims.questions else WRAP_UP_TEXT
        reply = f"Thanks for consenting. {first}"
        state.transcript.append(_entry(ROLE_ASSISTANT, reply, now))
        return {"assistant": reply, "declined": False, "done": False}

    def _acknowledge(self, claims: TokenClaims, question: str, answer: str) -> str:
        prompt = (
            f"TASK:interview venture={claims.venture_id}\n"
            "You are conducting a consent-based founder interview.\n"
            f"Question asked: {question}\n"
            f"Founder answered: {answer}\n"
            "Acknowledge the answer in one short sentence."
        )
        return self._llm.complete(prompt).text.strip()

    def message(self, token: str, session: str, text: str) -> dict[str, Json]:
        """Advance the chat by one founder message.

        The first message answers the consent prompt and is recorded verbatim;
        'skip' moves past the current question without an LLM turn.

        Args:
            token: The raw emailed token.
            session: The caller's device session id.
            text: The founder's message.

        Returns:
            The assistant's reply plus loop status.
        """
        claims, row = self._claims(token)
        state = self._state(claims, session)
        if not state.consent_confirmed:
            return self._record_consent(claims, state, text, row)
        now = self._clock()
        state.transcript.append(_entry(ROLE_FOUNDER, text, now))
        skipped = text.strip().lower() == SKIP_COMMAND
        asked = (
            claims.questions[state.question_index]
            if state.question_index < len(claims.questions)
            else WRAP_UP_TEXT
        )
        ack = "No problem, we'll skip that." if skipped else self._acknowledge(claims, asked, text)
        state.question_index += 1
        if state.question_index < len(claims.questions):
            reply = f"{ack} {claims.questions[state.question_index]}"
            done = False
        else:
            reply = f"{ack} {WRAP_UP_TEXT}"
            done = True
        state.transcript.append(_entry(ROLE_ASSISTANT, reply, self._clock()))
        return {"assistant": reply, "declined": False, "done": done}

    def _extract(self, claims: TokenClaims, state: _ActiveState) -> dict[str, Json]:
        transcript_text = "\n".join(
            f"{get_str(item, 'role')}: {get_str(item, 'text')}"
            for entry in state.transcript
            if (item := as_mapping(entry))
        )
        prompt = (
            f"TASK:interview_extract venture={claims.venture_id}\n"
            "Extract the structured interview payload (education, career, "
            "team_commitment, traction_claims, funding_status) from this "
            f"transcript as JSON:\n{transcript_text}"
        )
        response = self._llm.complete(prompt, schema=bundled_schema("interview"))
        if response.parsed is None:
            raise ExtractionInvalidError([])
        extracted = dict(response.parsed)
        errors = payload_errors("interview", extracted)
        if errors:
            raise ExtractionInvalidError(errors)
        return extracted

    def complete(self, token: str, session: str) -> dict[str, Json]:
        """Finish the interview: persist it, flip the outreach, rescore.

        Args:
            token: The raw emailed token (consumed by this call).
            session: The caller's device session id.

        Returns:
            Completion summary including the rescore status.

        Raises:
            ConsentRequiredError: If consent was never given.
        """
        claims, row = self._claims(token)
        state = self._state(claims, session)
        if not state.consent_confirmed:
            raise ConsentRequiredError
        extracted = self._extract(claims, state)
        now = self._clock()
        interview_row: dict[str, Json] = {
            "interview_id": self._id_factory(),
            "outreach_id": claims.outreach_id,
            "venture_id": claims.venture_id,
            "person_id": claims.person_id,
            "consent_confirmed": True,
            "started_at": (state.started_at or now).isoformat(),
            "completed_at": now.isoformat(),
            "transcript": list(state.transcript),
            "extracted": extracted,
            "model_version": self._model_version,
            "rescore_score_id": None,
            "updated_at": now.isoformat(),
        }
        self._persist_interview(interview_row)
        transition_outreach(
            self._store,
            row,
            OutreachTransition(
                status="interviewed", actor=claims.person_id, now=now, consent_at=None
            ),
        )
        outcome = self._rescore(interview_row)
        if outcome.score_rows:
            score_id = outcome.score_rows[0].get("score_id")
            interview_row["rescore_score_id"] = score_id if isinstance(score_id, str) else None
            self._persist_interview(interview_row)
        del self._active[claims.outreach_id]
        return {
            "interview_id": interview_row["interview_id"],
            "rescore_status": outcome.status,
            "rescore_score_id": interview_row["rescore_score_id"],
        }

    def _persist_interview(self, interview_row: dict[str, Json]) -> None:
        sink_row: dict[str, SinkValue] = {
            key: as_sink(value) for key, value in interview_row.items()
        }
        self._store.upsert("gold.interview", [sink_row])

    def opt_out(self, token: str) -> bool:
        """One-click opt-out: flip the matching outreach row to opted_out.

        Works regardless of expiry or current status so the link in the email
        always honors the request.

        Args:
            token: The raw token from the opt-out URL.

        Returns:
            True when a row was found and flipped.
        """
        hashed = token_hash(token)
        for row in self._store.rows("gold.outreach"):
            if row.get("token_hash") == hashed:
                step = OutreachTransition(
                    status="opted_out",
                    actor=get_str(row, "person_id") or "founder",
                    now=self._clock(),
                    consent_at=None,
                )
                transition_outreach(self._store, row, step)
                self._active.pop(get_str(row, "outreach_id") or "", None)
                return True
        return False
