"""Tests for OHLCV resampling and validation functions.

These test the in-process logic only; no ArcticDB connection needed.
"""

import pandas as pd
import pytest
from openbb_core.provider.abstract.data import Data
from openbb_core.app.model.abstract.error import OpenBBError

from openbb_arcticdb.models.historical import (
    _pandas_ohlcv,
    _resample_spec,
    _validate,
)


# ---------------------------------------------------------------------------
# _resample_spec
# ---------------------------------------------------------------------------

class TestResampleSpec:
    @pytest.mark.parametrize(
        ("interval", "expected"),
        [
            ("1m", "1min"),
            ("5m", "5min"),
            ("15M", "15ME"),        # uppercase M = month
            ("1h", "1h"),
            ("4h", "4h"),
            ("1d", "1D"),
            ("1D", "1D"),
            ("1w", "1W"),
            ("2w", "2W"),
            ("1mo", "1ME"),
            ("3mo", "3ME"),
            ("1M", "1ME"),           # uppercase M = month
            ("1mon", "1ME"),
            ("1month", "1ME"),
        ],
    )
    def test_valid(self, interval, expected):
        assert _resample_spec(interval) == expected

    @pytest.mark.parametrize(
        ("bad", "msg"),
        [
            ("", "Could not parse"),
            ("xyz", "Unsupported interval"),
            ("1xyz", "Unsupported interval"),
            ("abc", "Unsupported interval"),
        ],
    )
    def test_invalid_raises(self, bad, msg):
        with pytest.raises(OpenBBError, match=msg):
            _resample_spec(bad)


# ---------------------------------------------------------------------------
# _pandas_ohlcv
# ---------------------------------------------------------------------------

class TestPandasOhlcv:
    def test_resample_daily_to_weekly(self):
        dates = pd.date_range("2026-01-01", periods=15, freq="D")
        df = pd.DataFrame(
            {"open": range(1, 16), "high": range(2, 17), "low": range(0, 15), "close": range(1, 16), "volume": 100},
            index=dates,
        )
        out = _pandas_ohlcv(df, "1W")
        # 15 days from Thu Jan 1 spans 3 ISO weeks
        assert len(out) == 3
        assert out["open"].iloc[0] == 1
        assert out["close"].iloc[-1] == 15

    def test_price_column_only(self):
        dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])
        df = pd.DataFrame({"price": [10, 11, 12]}, index=dates)
        out = _pandas_ohlcv(df, "1D")
        assert len(out) == 3
        assert list(out.columns) == ["open", "high", "low", "close"]

    def test_price_and_volume(self):
        dates = pd.to_datetime(["2026-01-01", "2026-01-02"])
        df = pd.DataFrame({"price": [10, 11], "size": [100, 200]}, index=dates)
        out = _pandas_ohlcv(df, "1D")
        assert "volume" in out.columns
        assert out["volume"].iloc[0] == 100

    def test_drops_empty_buckets(self):
        dates = pd.to_datetime(["2026-01-01", "2026-01-05"])
        df = pd.DataFrame({"open": [1.0, 2.0], "close": [1.5, 2.5], "volume": [100, 200]}, index=dates)
        out = _pandas_ohlcv(df, "1D")
        # The gap day (Jan 2-4) has NaN OHLC — should be dropped
        assert len(out) == 2

    def test_case_insensitive_columns(self):
        dates = pd.to_datetime(["2026-01-01", "2026-01-02"])
        df = pd.DataFrame({"Open": [1.0, 2.0], "Close": [1.5, 2.5]}, index=dates)
        out = _pandas_ohlcv(df, "1D")
        assert "open" in out.columns
        assert "Open" not in out.columns

    def test_full_ohlc_capitalized_columns(self):
        # Full OHLCV with capitalized headers (e.g. raw yfinance / CSV import)
        # must resample to canonical lowercase columns so the standard models
        # can populate open/high/low/close/volume.
        dates = pd.date_range("2026-01-01", periods=4, freq="D")
        df = pd.DataFrame(
            {
                "Open": [1.0, 2.0, 3.0, 4.0],
                "High": [2.0, 3.0, 4.0, 5.0],
                "Low": [0.0, 1.0, 2.0, 3.0],
                "Close": [1.5, 2.5, 3.5, 4.5],
                "Volume": [10, 20, 30, 40],
            },
            index=dates,
        )
        out = _pandas_ohlcv(df, "2D")
        assert list(out.columns) == ["open", "high", "low", "close", "volume"]
        assert not any(str(c)[0].isupper() for c in out.columns)


# ---------------------------------------------------------------------------
# _validate
# ---------------------------------------------------------------------------

class TestValidate:
    def test_strips_nan_floats(self):
        data = [{"date": "2026-01-01", "close": 100.0, "open": float("nan")}]
        result = _validate(None, data, Data)
        assert len(result) == 1
        assert "open" not in result[0].model_dump()

    def test_strips_none(self):
        data = [{"date": "2026-01-01", "close": None, "open": 100.0}]
        result = _validate(None, data, Data)
        assert len(result) == 1
        assert "close" not in result[0].model_dump()

    def test_sorts_by_symbol_then_date(self):
        data = [
            {"date": "2026-01-03", "close": 3.0, "symbol": "B"},
            {"date": "2026-01-01", "close": 1.0, "symbol": "A"},
            {"date": "2026-01-02", "close": 2.0, "symbol": "A"},
        ]
        result = _validate(None, data, Data)
        assert str(result[0].date) == "2026-01-01"
        assert result[0].symbol == "A"
        assert result[2].symbol == "B"

    def test_passes_through_valid(self):
        data = [{"date": "2026-01-01", "close": 100.0}]
        result = _validate(None, data, Data)
        assert result[0].close == 100.0
