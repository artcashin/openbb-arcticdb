"""Generic read/write API for arbitrary OpenBB / DataFrame data in ArcticDB.

The `provider="arcticdb"` path is bound to OpenBB's fixed OHLCV models. This
store handles *any* shape of data — economy series, fundamentals, screeners,
plain DataFrames — and is the generic counterpart to the `.arcticdb` accessor.

    from openbb_arcticdb import store
    s = store(library="research")          # uri/library default to env/LMDB
    s.write("gdp", obb.economy.gdp.real(provider="oecd"))   # OBBject, DataFrame, or records
    s.write("notes", my_dataframe)
    df  = s.read("gdp", output="dataframe")
    obj = s.read("gdp")                     # OBBject (default) -> .to_df(), charting, etc.
    s.list_symbols(); s.has("gdp"); s.read_metadata("gdp"); s.delete("gdp")
"""

from typing import Any, Optional, Sequence


class ArcticStore:
    """Generic ArcticDB store for arbitrary tabular data."""

    def __init__(self, uri: Optional[str] = None, library: Optional[str] = None):
        """Resolve the connection (uri/library) from args, env, or defaults."""
        # pylint: disable=import-outside-toplevel
        from openbb_arcticdb.utils import resolve_config

        self.uri, self.library = resolve_config(uri, library, None)

    # -- helpers ------------------------------------------------------------
    def _lib(self, create_if_missing: bool = True):
        # pylint: disable=import-outside-toplevel
        from openbb_arcticdb.utils import get_library

        return get_library(self.uri, self.library, create_if_missing=create_if_missing)

    @staticmethod
    def _to_frame(data: Any):
        """Accept an OBBject, DataFrame, or records and return a storable frame."""
        # pylint: disable=import-outside-toplevel
        from pandas import DataFrame

        from openbb_arcticdb.utils import normalize_index

        if hasattr(data, "to_dataframe"):  # OBBject
            df = data.to_dataframe()
        elif isinstance(data, DataFrame):
            df = data.copy()
        else:  # list[dict] / dict / array-like
            df = DataFrame(data)
        if df is None or df.empty:
            raise ValueError("No data to write to ArcticDB.")
        return normalize_index(df)

    @staticmethod
    def _to_obbject(df, key: Optional[str], metadata: Any, library: str):
        """Wrap a stored frame in a generic OBBject."""
        # pylint: disable=import-outside-toplevel
        from pandas import RangeIndex

        from openbb_core.app.model.obbject import OBBject
        from openbb_core.provider.abstract.data import Data

        out = df.reset_index(drop=isinstance(df.index, RangeIndex))
        results = [
            Data.model_validate(
                {k: v for k, v in rec.items() if not (isinstance(v, float) and v != v)}
            )
            for rec in out.to_dict("records")
        ]
        return OBBject(
            results=results,
            provider="arcticdb",
            extra={"symbol": key, "library": library, "metadata": metadata},
        )

    # -- write --------------------------------------------------------------
    def write(
        self,
        key: str,
        data: Any,
        *,
        metadata: Optional[dict] = None,
        prune_previous_versions: bool = False,
    ) -> dict[str, Any]:
        """Write any data as a new version of `key` (overwrites the symbol)."""
        df = self._to_frame(data)
        v = self._lib().write(
            key, df, metadata=metadata, prune_previous_versions=prune_previous_versions
        )
        return {
            "uri": self.uri,
            "library": self.library,
            "symbol": key,
            "version": getattr(v, "version", None),
            "rows": int(len(df)),
        }

    def append(self, key: str, data: Any) -> dict[str, Any]:
        """Append data to an existing symbol."""
        df = self._to_frame(data)
        v = self._lib().append(key, df)
        return {
            "uri": self.uri,
            "library": self.library,
            "symbol": key,
            "version": getattr(v, "version", None),
            "rows_appended": int(len(df)),
        }

    # -- read ---------------------------------------------------------------
    def read(
        self,
        key: str,
        *,
        start_date: Any = None,
        end_date: Any = None,
        columns: Optional[Sequence[str]] = None,
        as_of: Any = None,
        output: str = "obbject",
    ):
        """Read `key`; returns an OBBject (default) or a DataFrame (`output='dataframe'`).

        `start_date` / `end_date` accept date, datetime, or string (a pure date
        `end` is treated as inclusive of the whole day).
        """
        # pylint: disable=import-outside-toplevel
        from openbb_arcticdb.utils import to_bounds

        lib = self._lib(create_if_missing=False)
        start_ts, end_ts = to_bounds(start_date, end_date)
        date_range = None if start_ts is None and end_ts is None else (start_ts, end_ts)
        item = lib.read(
            key,
            date_range=date_range,
            columns=list(columns) if columns else None,
            as_of=as_of,
        )
        if output == "dataframe":
            return item.data
        return self._to_obbject(item.data, key, item.metadata, self.library)

    # -- catalog ------------------------------------------------------------
    def list_symbols(self) -> list[str]:
        """List symbols in the library."""
        return list(self._lib().list_symbols())

    def has(self, key: str) -> bool:
        """Whether `key` exists (False if the library doesn't exist yet)."""
        try:
            return self._lib(create_if_missing=False).has_symbol(key)
        except FileNotFoundError:
            return False

    def delete(self, key: str) -> dict[str, Any]:
        """Delete a symbol."""
        self._lib().delete(key)
        return {"uri": self.uri, "library": self.library, "deleted": key}

    def read_metadata(self, key: str) -> Any:
        """Read just the metadata stored alongside `key`."""
        return self._lib(create_if_missing=False).read_metadata(key).metadata


def store(uri: Optional[str] = None, library: Optional[str] = None) -> ArcticStore:
    """Convenience factory: `store(library="research")`."""
    return ArcticStore(uri=uri, library=library)
