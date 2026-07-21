"""The VC login gate: password login mints in-memory bearer session tokens.

Interview routes are NOT gated here — founders authenticate by outreach token
(app.interview); everything else under /v1 requires a minted session.
"""

import os
import secrets
from typing import Final

from tools.settings import MissingConfigError

PASSWORD_ENV: Final[str] = "APP_PASSWORD"  # noqa: S105 - env var name, not a credential
FIXTURES_PASSWORD: Final[str] = "demo"  # noqa: S105 - fixtures-mode default, overridable via APP_PASSWORD
SESSION_TOKEN_BYTES: Final[int] = 16
_BEARER_PREFIX: Final[str] = "bearer "


def resolve_password(*, fixtures: bool) -> str:
    """The app password: APP_PASSWORD env, or the fixtures default.

    Args:
        fixtures: Whether the app runs in credential-free fixtures mode.

    Returns:
        The password to gate /v1 with.

    Raises:
        MissingConfigError: If live mode has no APP_PASSWORD set.
    """
    configured = os.environ.get(PASSWORD_ENV)
    if configured:
        return configured
    if fixtures:
        return FIXTURES_PASSWORD
    raise MissingConfigError([PASSWORD_ENV])


def bearer_token(authorization: str | None) -> str | None:
    """Extract the token from an Authorization: Bearer header value.

    Args:
        authorization: The raw header value, if any.

    Returns:
        The token, or None when the header is absent or malformed.
    """
    if authorization is None or not authorization.lower().startswith(_BEARER_PREFIX):
        return None
    return authorization[len(_BEARER_PREFIX) :].strip() or None


class SessionRegistry:
    """In-memory session tokens for the VC UI (single-process demo scope)."""

    def __init__(self, password: str) -> None:
        """Bind the shared password; no sessions exist yet."""
        self._password: Final[str] = password
        self._tokens: Final[set[str]] = set()

    def login(self, password: str) -> str | None:
        """Mint a session token for a correct password.

        Args:
            password: The submitted password.

        Returns:
            A fresh bearer token, or None when the password is wrong.
        """
        if not secrets.compare_digest(password, self._password):
            return None
        token = secrets.token_hex(SESSION_TOKEN_BYTES)
        self._tokens.add(token)
        return token

    def is_valid(self, token: str | None) -> bool:
        """Whether the token names a live session.

        Args:
            token: The presented bearer token, if any.

        Returns:
            True for a minted, still-valid session token.
        """
        return token is not None and token in self._tokens
