# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Fail-fast runtime configuration: explicit env keys, no silent fallbacks."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

REQUIRED_ENV_KEYS: Final[tuple[str, str, str, str]] = (
    "DATABRICKS_HOST",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
    "DATABRICKS_WAREHOUSE_ID",
)


class MissingConfigError(RuntimeError):
    """Raised when required environment keys are absent."""

    def __init__(self, keys: list[str]) -> None:
        """Name the absent keys in the message."""
        super().__init__(f"missing required config: {', '.join(keys)} (see .env.example)")


@dataclass(frozen=True, slots=True)
class DatabricksSettings:
    """Service-principal M2M OAuth credentials for the SQL warehouse."""

    host: str
    client_id: str
    client_secret: str
    warehouse_id: str

    @property
    def server_hostname(self) -> str:
        """Hostname without the https scheme, as the connector expects."""
        return self.host.removeprefix("https://").removeprefix("http://").rstrip("/")

    @property
    def http_path(self) -> str:
        """Warehouse HTTP path for the SQL connector."""
        return f"/sql/1.0/warehouses/{self.warehouse_id}"


def load_databricks_settings(env_file: Path | None = None) -> DatabricksSettings:
    """Load settings from the environment, reading `.env` first.

    Args:
        env_file: Alternative dotenv file, mainly for tests.

    Returns:
        The validated settings.

    Raises:
        MissingConfigError: If any required key is absent or empty.
    """
    load_dotenv(dotenv_path=env_file)
    missing = [key for key in REQUIRED_ENV_KEYS if not os.environ.get(key)]
    if missing:
        raise MissingConfigError(missing)
    return DatabricksSettings(
        host=os.environ["DATABRICKS_HOST"],
        client_id=os.environ["DATABRICKS_CLIENT_ID"],
        client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
        warehouse_id=os.environ["DATABRICKS_WAREHOUSE_ID"],
    )
