"""ArcticDB connection helpers shared by the provider and the OBBject accessor."""

import os
from typing import Any


def default_uri() -> str:
    """Default LMDB store under the OpenBB home directory."""
    home = os.getenv("OPENBB_HOME") or os.path.expanduser("~/.openbb_platform")
    return f"lmdb://{os.path.join(home, 'arcticdb')}"


def resolve_config(
    uri: str | None = None,
    library: str | None = None,
    credentials: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Resolve the ArcticDB URI and library name.

    Precedence: explicit arg > OpenBB credential > environment variable > default.
    """
    creds = credentials or {}
    uri = (
        uri
        or creds.get("arcticdb_uri")
        or os.getenv("ARCTICDB_URI")
        or default_uri()
    )
    library = (
        library
        or creds.get("arcticdb_library")
        or os.getenv("ARCTICDB_LIBRARY")
        or "openbb"
    )
    return uri, library


def normalize_index(df):
    """Coerce a date/`datetime.date` column or index into a sorted DatetimeIndex.

    ArcticDB cannot normalize `datetime.date` values and stores time series most
    usefully with a DatetimeIndex (enables `date_range` filtering on read). Frames
    without any date-like index are returned unchanged.
    """
    # pylint: disable=import-outside-toplevel
    from pandas import DatetimeIndex, RangeIndex, to_datetime
    from pandas.api.types import is_numeric_dtype

    if isinstance(df.index, DatetimeIndex):
        return df.sort_index()

    # Explicit 'date' column wins.
    if "date" in df.columns:
        df = df.set_index("date")
        try:
            df.index = to_datetime(df.index)
            return df.sort_index()
        except (ValueError, TypeError):
            return df

    # Only coerce a genuinely date-like index. A numeric / RangeIndex is
    # positional (e.g. screener rows) — to_datetime would turn 0,1,2 into bogus
    # 1970 timestamps, so leave it alone.
    if not isinstance(df.index, RangeIndex) and not is_numeric_dtype(df.index):
        try:
            df.index = to_datetime(df.index)
            return df.sort_index()
        except (ValueError, TypeError):
            return df
    return df


def parse_temporal(v: Any):
    """Coerce str/date/datetime into a date or datetime, preserving the time-of-day.

    A string with a time component (`2026-06-01 09:30`) becomes a datetime; a
    date-only string (`2026-06-01`) becomes a date. date/datetime objects pass
    through unchanged. This lets start/end accept BOTH dates and datetimes.
    """
    # pylint: disable=import-outside-toplevel
    from datetime import date as dateType, datetime

    if v is None or isinstance(v, datetime):
        return v
    if isinstance(v, dateType):
        return v
    if isinstance(v, str):
        from dateutil import parser

        tail = v.split("T", 1)[1] if "T" in v else ""
        has_time = (":" in v) or any(ch.isdigit() for ch in tail)
        dt = parser.parse(v)
        return dt if has_time else dt.date()
    return v


def to_bounds(start: Any, end: Any):
    """Return (start_ts, end_ts) pandas Timestamps for an ArcticDB `date_range`.

    A pure-date `end` is widened to end-of-day so the whole day is inclusive
    (matters for intraday/tick data); a datetime `end` is used exactly.
    """
    # pylint: disable=import-outside-toplevel
    from datetime import date as dateType, datetime

    from pandas import Timedelta, Timestamp

    s = parse_temporal(start)
    e = parse_temporal(end)
    start_ts = None if s is None else Timestamp(s)
    if e is None:
        end_ts = None
    else:
        end_ts = Timestamp(e)
        if isinstance(e, dateType) and not isinstance(e, datetime):
            end_ts = end_ts.normalize() + Timedelta(days=1) - Timedelta(nanoseconds=1)
    return start_ts, end_ts


def get_library(uri: str, library: str, create_if_missing: bool = True):
    """Open (and optionally create) an ArcticDB library."""
    # pylint: disable=import-outside-toplevel
    from arcticdb import Arctic

    # LMDB needs the target directory to exist before connecting.
    if uri.startswith("lmdb://"):
        path = uri[len("lmdb://") :]
        if path:
            os.makedirs(path, exist_ok=True)

    ac = Arctic(uri)
    if not create_if_missing and not ac.has_library(library):
        raise FileNotFoundError(
            f"ArcticDB library '{library}' does not exist at '{uri}'. "
            "Write some data first with `result.arcticdb.write(...)`."
        )
    return ac.get_library(library, create_if_missing=create_if_missing)
