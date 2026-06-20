"""ArcticDB OBBject accessor (write path).

Attaches an `.arcticdb` namespace to every OBBject result so any query can be
persisted to ArcticDB and managed:

    res = obb.equity.price.historical("AAPL", provider="yfinance")
    res.arcticdb.write("AAPL")                 # store into the default library
    res.arcticdb.append("AAPL")                # append new rows
    res.arcticdb.list_symbols()                # catalog
    res.arcticdb.read_metadata("AAPL")
    res.arcticdb.delete("AAPL")

All methods accept optional `library=` / `uri=` overrides. For reading arbitrary
data back (and for use without an existing result), see `openbb_arcticdb.store`.
"""

from typing import Any, Optional


class ArcticDBAccessor:
    """Persist and manage OBBject results in ArcticDB."""

    def __init__(self, obbject):
        """Bind the accessor to its OBBject."""
        self._obbject = obbject

    @staticmethod
    def _store(uri: Optional[str], library: Optional[str]):
        # pylint: disable=import-outside-toplevel
        from openbb_arcticdb.store import ArcticStore

        return ArcticStore(uri=uri, library=library)

    def write(
        self,
        key: str,
        *,
        library: Optional[str] = None,
        uri: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        prune_previous_versions: bool = False,
    ) -> dict[str, Any]:
        """Write this result to ArcticDB as a new version (overwrites the symbol)."""
        return self._store(uri, library).write(
            key,
            self._obbject,
            metadata=metadata,
            prune_previous_versions=prune_previous_versions,
        )

    def append(
        self, key: str, *, library: Optional[str] = None, uri: Optional[str] = None
    ) -> dict[str, Any]:
        """Append this result to an existing symbol."""
        return self._store(uri, library).append(key, self._obbject)

    def list_symbols(
        self, *, library: Optional[str] = None, uri: Optional[str] = None
    ) -> list[str]:
        """List symbols stored in the library."""
        return self._store(uri, library).list_symbols()

    def read_metadata(
        self, key: str, *, library: Optional[str] = None, uri: Optional[str] = None
    ) -> Any:
        """Read the metadata stored alongside `key`."""
        return self._store(uri, library).read_metadata(key)

    def delete(
        self, key: str, *, library: Optional[str] = None, uri: Optional[str] = None
    ) -> dict[str, Any]:
        """Delete a symbol from the library."""
        return self._store(uri, library).delete(key)
