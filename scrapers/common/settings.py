"""Scraper-side configuration, separate from the WS0 Databricks settings.

Only the contact email is unconditionally required (it goes into every
User-Agent per API etiquette); source-specific keys are validated by the
command that needs them, so a papers dev never needs a GitHub token and
the credential-free CI path (`--fixtures --dry-run`) needs no env at all.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

from tools.settings import MissingConfigError

CONTACT_ENV_KEY: Final[str] = "SCRAPER_CONTACT_EMAIL"
OFFLINE_CONTACT_EMAIL: Final[str] = "offline@example.invalid"
USER_AGENT_TEMPLATE: Final[str] = "dealflow-scraper/0.1 (+mailto:{contact})"


@dataclass(frozen=True, slots=True)
class ScraperSettings:
    """Per-dev scraper credentials; None means the key was not configured."""

    contact_email: str
    github_token: str | None
    openalex_api_key: str | None
    s2_api_key: str | None

    @property
    def user_agent(self) -> str:
        """The descriptive User-Agent sent on every scraper request."""
        return USER_AGENT_TEMPLATE.format(contact=self.contact_email)


def load_scraper_settings(env_file: Path | None = None) -> ScraperSettings:
    """Load scraper settings from the environment, reading `.env` first.

    Args:
        env_file: Alternative dotenv file, mainly for tests.

    Returns:
        The settings; source keys stay None when absent.

    Raises:
        MissingConfigError: If the contact email is absent or empty.
    """
    load_dotenv(dotenv_path=env_file)
    contact = os.environ.get(CONTACT_ENV_KEY)
    if not contact:
        raise MissingConfigError([CONTACT_ENV_KEY])
    return ScraperSettings(
        contact_email=contact,
        github_token=os.environ.get("GITHUB_TOKEN") or None,
        openalex_api_key=os.environ.get("OPENALEX_API_KEY") or None,
        s2_api_key=os.environ.get("S2_API_KEY") or None,
    )


def offline_scraper_settings() -> ScraperSettings:
    """Dummy settings for fixture replay in dry-run mode; reads no env.

    Returns:
        Settings with a placeholder contact and no source keys.
    """
    return ScraperSettings(
        contact_email=OFFLINE_CONTACT_EMAIL,
        github_token=None,
        openalex_api_key=None,
        s2_api_key=None,
    )


def require_key(value: str | None, env_key: str) -> str:
    """Fail fast when a live command needs a source key that is not set.

    Args:
        value: The loaded (possibly absent) key value.
        env_key: The env variable name, for the error message.

    Returns:
        The non-empty key value.

    Raises:
        MissingConfigError: If the value is None or empty.
    """
    if not value:
        raise MissingConfigError([env_key])
    return value
