"""The single typed seam to the Databricks SQL warehouse.

The vendor connector ships no complete type information, so every untyped
touchpoint is confined to this module behind small Protocols.
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Final, Protocol, cast

import databricks.sql as dbsql  # pyright: ignore[reportMissingTypeStubs] - vendor ships no stubs
from databricks.sdk.core import Config
from databricks.sdk.credentials_provider import OAuthCredentialsProvider, oauth_service_principal
from databricks.sql.exc import (  # pyright: ignore[reportMissingTypeStubs] - vendor ships no stubs
    Error as WarehouseError,
)

from tools.settings import DatabricksSettings

__all__ = ["CursorLike", "Warehouse", "WarehouseError"]


class CursorLike(Protocol):
    """The connector-cursor surface the platform code relies on."""

    def execute(self, operation: str) -> object:
        """Run one SQL statement."""
        ...

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return all rows of the last statement."""
        ...

    def close(self) -> None:
        """Release the cursor."""
        ...


class _ConnectionLike(Protocol):
    def cursor(self) -> CursorLike: ...
    def close(self) -> None: ...


class Warehouse:
    """Connection factory bound to one warehouse via M2M OAuth."""

    _settings: Final[DatabricksSettings]

    def __init__(self, settings: DatabricksSettings) -> None:
        """Bind to one workspace and warehouse."""
        self._settings = settings

    def _credentials_provider(self) -> OAuthCredentialsProvider:
        """Mint OAuth headers; passed as a zero-arg callable to the connector."""
        config = Config(
            host=self._settings.host,
            client_id=self._settings.client_id,
            client_secret=self._settings.client_secret,
        )
        return oauth_service_principal(config)

    def _connect(self) -> _ConnectionLike:
        raw: object = dbsql.connect(  # pyright: ignore[reportUnknownMemberType] - vendor API is partially typed
            server_hostname=self._settings.server_hostname,
            http_path=self._settings.http_path,
            credentials_provider=self._credentials_provider,
        )
        return cast("_ConnectionLike", cast("object", raw))

    @contextmanager
    def cursor(self) -> Generator[CursorLike]:
        """Yield a live cursor, closing connection and cursor afterwards.

        Yields:
            An open cursor against the configured warehouse.
        """
        connection = self._connect()
        cursor = connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()
            connection.close()

    def execute(self, statement: str) -> list[tuple[object, ...]]:
        """Run a single statement on a fresh cursor and fetch all rows.

        Args:
            statement: The SQL text to run.

        Returns:
            All result rows (empty for DDL).
        """
        with self.cursor() as cursor:
            cursor.execute(statement)
            return cursor.fetchall()
