"""ArcticDB historical price models (read path).

Serves OHLCV bars previously persisted to an ArcticDB library back through the
standard OpenBB interface, for several asset classes:
`obb.equity.price.historical(provider="arcticdb")`,
`obb.crypto.price.historical(provider="arcticdb")`, etc.

For arbitrary (non-OHLCV) data, use the generic `openbb_arcticdb.store` API.
"""

# pylint: disable=unused-argument

from datetime import date as dateType, datetime
from typing import Any, List, Optional, Union

from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.standard_models.crypto_historical import (
    CryptoHistoricalData,
    CryptoHistoricalQueryParams,
)
from openbb_core.provider.standard_models.currency_historical import (
    CurrencyHistoricalData,
    CurrencyHistoricalQueryParams,
)
from openbb_core.provider.standard_models.equity_historical import (
    EquityHistoricalData,
    EquityHistoricalQueryParams,
)
from openbb_core.provider.standard_models.etf_historical import (
    EtfHistoricalData,
    EtfHistoricalQueryParams,
)
from openbb_core.provider.standard_models.index_historical import (
    IndexHistoricalData,
    IndexHistoricalQueryParams,
)
from openbb_core.app.model.abstract.error import OpenBBError
from openbb_core.provider.utils.errors import EmptyDataError
from pydantic import Field, field_validator

# Aggregators that turn a group of rows into one OHLCV bar.
_OHLC = (("open", "first"), ("high", "max"), ("low", "min"), ("close", "last"))


def _resample_spec(interval: str) -> tuple[str, Optional[str]]:
    """Map an interval to (arctic_native_rule, pandas_rule).

    ArcticDB resamples natively only up to days (s, min, h, D). Weeks and months
    are done with a second pandas resample on the daily bars, so this returns a
    native rule for ArcticDB plus an optional pandas rule to apply afterwards.

    Note: lowercase 'm' is MINUTE (1m, 5m); month is 'mo'/'mon'/'month' or
    uppercase 'M' (1mo, 3mo, 1M); week is 'w'/'wk'/'week' (1w, 2w).
    """
    # pylint: disable=import-outside-toplevel
    import re

    s = str(interval).strip()
    m = re.fullmatch(r"(\d*)\s*([a-zA-Z]+)", s)
    if not m:
        raise OpenBBError(f"Could not parse interval '{interval}'.")
    n = m.group(1) or "1"
    raw_unit = m.group(2)
    unit = raw_unit.lower()

    # Month: uppercase 'M' (distinct from minute) or explicit month words.
    if raw_unit == "M" or unit in {"mo", "mon", "month", "months", "mth"}:
        return "1D", f"{n}ME"  # daily server-side, then pandas month-end
    if unit in {"w", "wk", "week", "weeks"}:
        return "1D", f"{n}W"  # daily server-side, then pandas weekly
    native = {
        "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
        "m": "min", "min": "min", "mins": "min", "minute": "min", "minutes": "min", "t": "min",
        "h": "h", "hr": "h", "hour": "h", "hours": "h",
        "d": "D", "day": "D", "days": "D",
    }.get(unit)
    if native is None:
        raise OpenBBError(
            f"Unsupported interval '{interval}'. Supported: seconds (s), minutes "
            "(m/min), hours (h), days (d), weeks (w), months (mo/M) — e.g. '1m', "
            "'5m', '1h', '1d', '1w', '2w', '1mo', '3mo'."
        )
    return f"{n}{native}", None


def _pandas_ohlcv(df, rule: str, origin: str = "start_day"):
    """Resample daily OHLCV bars into a coarser (weekly/monthly) frame with pandas."""
    cl = {str(c).lower(): c for c in df.columns}
    agg = {cl[k]: fn for k, fn in _OHLC if k in cl}
    if "volume" in cl:
        agg[cl["volume"]] = "sum"
    out = df.resample(rule, origin=origin).agg(agg)
    # Drop empty buckets (e.g. gaps): sum() volume is 0 but OHLC are NaN.
    subset = [cl[k] for k in ("close", "open") if k in cl]
    return out.dropna(subset=subset) if subset else out.dropna(how="all")


def _ohlcv_agg(columns) -> dict:
    """Build a resample aggregation from whatever columns the symbol has.

    Downsamples existing OHLCV, or aggregates tick data (a price column + an
    optional size/volume column) into OHLCV.
    """
    cl = {str(c).lower(): c for c in columns}
    if {"open", "high", "low", "close"} <= set(cl):
        agg = {k: (cl[k], fn) for k, fn in _OHLC}
        if "volume" in cl:
            agg["volume"] = (cl["volume"], "sum")
        return agg
    price = next((cl[c] for c in ("price", "last", "close", "trade_price", "p") if c in cl), None)
    if price is None:
        raise OpenBBError(
            "Cannot resample to OHLCV: symbol has neither OHLC columns nor a "
            "recognizable price column (price/last/close)."
        )
    agg = {k: (price, fn) for k, fn in _OHLC}
    vol = next((cl[c] for c in ("size", "volume", "qty", "quantity", "amount", "v") if c in cl), None)
    if vol is not None:
        agg["volume"] = (vol, "sum")
    return agg


async def _extract_bars(query, credentials: Optional[dict]) -> list[dict]:
    """Read raw bars for one or more symbols from an ArcticDB library."""
    # pylint: disable=import-outside-toplevel
    import asyncio

    from openbb_arcticdb.utils import get_library, resolve_config, to_bounds

    uri, library = resolve_config(
        getattr(query, "uri", None), getattr(query, "library", None), credentials
    )
    symbols = [s.strip().upper() for s in query.symbol.split(",")]
    multiple = len(symbols) > 1
    # No interval -> assume daily. (OpenBB also strips interval=="1d" since it's the
    # global default, so an absent interval most often means the caller asked for 1d.)
    interval = getattr(query, "interval", None) or "1d"
    native_rule, pandas_rule = _resample_spec(interval)
    # Bucket anchoring: pandas default (start_day) vs ArcticDB epoch.
    pandas_anchor = bool(getattr(query, "pandas_anchor", False))
    start_ts, end_ts = to_bounds(query.start_date, query.end_date)

    def _read() -> list[dict]:
        # pylint: disable=import-outside-toplevel
        from arcticdb import QueryBuilder

        lib = get_library(uri, library, create_if_missing=False)
        rng = None if start_ts is None and end_ts is None else (start_ts, end_ts)
        out: list[dict] = []
        missing: list[str] = []
        for sym in symbols:
            if not lib.has_symbol(sym):
                missing.append(sym)
                continue
            # Resample (tick or finer bars) -> OHLCV at the native rule, server-side.
            head = lib.read(sym, row_range=(0, 1)).data
            # ArcticDB rejects string origins (e.g. 'start_day') together with a
            # date_range, so emulate pandas 'start_day' with a midnight Timestamp.
            if pandas_anchor:
                ref = start_ts if start_ts is not None else (
                    head.index[0] if len(head.index) else None
                )
                origin = ref.normalize() if ref is not None else "epoch"
            else:
                origin = "epoch"
            qb = QueryBuilder().resample(native_rule, origin=origin).agg(
                _ohlcv_agg(head.columns)
            )
            df = lib.read(sym, date_range=rng, query_builder=qb).data
            # Weeks/months: pandas re-resample the daily bars (ArcticDB stops at D).
            if pandas_rule and df is not None and not df.empty:
                df = _pandas_ohlcv(df, pandas_rule, origin=origin)
            if df is None or df.empty:
                continue
            df = df.reset_index()
            if "date" not in df.columns:
                df = df.rename(columns={df.columns[0]: "date"})
            records = df.to_dict("records")
            if multiple:
                for rec in records:
                    rec["symbol"] = sym
            out.extend(records)
        if not out:
            detail = f" Unknown symbols: {missing}." if missing else ""
            raise EmptyDataError(f"No data in ArcticDB library '{library}'.{detail}")
        return out

    return await asyncio.to_thread(_read)


def _validate(query, data: list[dict], data_cls):
    """Validate raw records against a (permissive) standard data model."""
    results = []
    for rec in data:
        clean = {
            k: v
            for k, v in rec.items()
            if v is not None and not (isinstance(v, float) and v != v)
        }
        results.append(data_cls.model_validate(clean))
    results.sort(key=lambda r: (str(getattr(r, "symbol", "")), r.date))
    return results


def _build_fetcher(label: str, qp_base, data_base):
    """Create an ArcticDB Fetcher for a given OHLCV standard model."""

    class _QP(qp_base):  # type: ignore[valid-type, misc]
        __json_schema_extra__ = {"symbol": {"multiple_items_allowed": True}}
        library: Optional[str] = Field(
            default=None,
            description="ArcticDB library to read from. Defaults to ARCTICDB_LIBRARY or 'openbb'.",
        )
        uri: Optional[str] = Field(
            default=None,
            description="ArcticDB connection URI. Defaults to ARCTICDB_URI or a local LMDB store.",
        )
        interval: Optional[str] = Field(
            default=None,
            description=(
                "Resample the stored symbol into OHLCV bars at this interval: "
                "seconds (1s), minutes (1m/5m), hours (1h), days (1d), weeks "
                "(1w/2w), months (1mo/3mo or 1M/3M). Works on tick data "
                "(price/size) or downsamples finer bars. Defaults to '1d' if omitted."
            ),
        )
        pandas_anchor: bool = Field(
            default=False,
            description=(
                "Bucket anchoring for resampling. False (default) uses ArcticDB's "
                "epoch anchor (origin='epoch'); True uses the pandas default anchor "
                "(origin='start_day'). Affects where bar boundaries fall."
            ),
        )
        # Widen start/end to accept BOTH date and datetime (the standard models
        # type these as date-only, which would drop the time component).
        start_date: Optional[Union[datetime, dateType]] = Field(
            default=None, description="Start date or datetime (inclusive)."
        )
        end_date: Optional[Union[datetime, dateType]] = Field(
            default=None, description="End date or datetime (inclusive)."
        )

        @field_validator("start_date", "end_date", mode="before")
        @classmethod
        def _coerce_temporal(cls, v):
            # pylint: disable=import-outside-toplevel
            from openbb_arcticdb.utils import parse_temporal

            return parse_temporal(v)

    _QP.__name__ = f"ArcticDB{label}QueryParams"

    class _Data(data_base):  # type: ignore[valid-type, misc]
        pass

    _Data.__name__ = f"ArcticDB{label}Data"

    class _Fetcher(Fetcher[_QP, List[_Data]]):
        @staticmethod
        def transform_query(params: dict[str, Any]) -> _QP:
            return _QP(**params)

        @staticmethod
        async def aextract_data(query, credentials, **kwargs) -> list[dict]:
            return await _extract_bars(query, credentials)

        @staticmethod
        def transform_data(query, data, **kwargs):
            return _validate(query, data, _Data)

    _Fetcher.__name__ = f"ArcticDB{label}Fetcher"
    return _Fetcher


ArcticDBEquityHistoricalFetcher = _build_fetcher(
    "EquityHistorical", EquityHistoricalQueryParams, EquityHistoricalData
)
ArcticDBEtfHistoricalFetcher = _build_fetcher(
    "EtfHistorical", EtfHistoricalQueryParams, EtfHistoricalData
)
ArcticDBCryptoHistoricalFetcher = _build_fetcher(
    "CryptoHistorical", CryptoHistoricalQueryParams, CryptoHistoricalData
)
ArcticDBCurrencyHistoricalFetcher = _build_fetcher(
    "CurrencyHistorical", CurrencyHistoricalQueryParams, CurrencyHistoricalData
)
ArcticDBIndexHistoricalFetcher = _build_fetcher(
    "IndexHistorical", IndexHistoricalQueryParams, IndexHistoricalData
)
