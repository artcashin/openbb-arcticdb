"""Tests for ArcticStore round-trips (requires a temporary LMDB)."""

import pandas as pd
import pytest

from openbb_arcticdb.store import ArcticStore


def _df():
    return pd.DataFrame(
        {"open": [1.0, 2.0], "high": [3.0, 4.0], "low": [0.5, 1.5], "close": [2.0, 3.0], "volume": [100, 200]},
        index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
    )


class TestWriteRead:
    def test_write_and_read_dataframe(self, store: ArcticStore):
        store.write("AAPL", _df())
        df = store.read("AAPL", output="dataframe")
        assert len(df) == 2
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    def test_read_as_obbject(self, store: ArcticStore):
        store.write("AAPL", _df())
        obj = store.read("AAPL")
        assert len(obj.results) == 2
        assert obj.provider == "arcticdb"
        assert obj.extra["symbol"] == "AAPL"

    def test_read_with_date_range(self, store: ArcticStore):
        store.write("AAPL", _df())
        df = store.read("AAPL", start_date="2026-01-02", output="dataframe")
        assert len(df) == 1

    def test_read_with_columns(self, store: ArcticStore):
        store.write("AAPL", _df())
        df = store.read("AAPL", columns=["close"], output="dataframe")
        assert list(df.columns) == ["close"]

    def test_read_nonexistent(self, store: ArcticStore):
        with pytest.raises(Exception):
            store.read("NONEXIST", output="dataframe")


class TestAppend:
    def test_append(self, store: ArcticStore):
        store.write("AAPL", _df())
        more = pd.DataFrame(
            {"open": [3.0, 4.0], "high": [5.0, 6.0], "low": [2.0, 3.0], "close": [4.0, 5.0], "volume": [300, 400]},
            index=pd.to_datetime(["2026-01-03", "2026-01-04"]),
        )
        store.append("AAPL", more)
        df = store.read("AAPL", output="dataframe")
        assert len(df) == 4


class TestCatalog:
    def test_list_symbols(self, store: ArcticStore):
        store.write("AAPL", _df())
        store.write("MSFT", _df())
        symbols = store.list_symbols()
        assert set(symbols) == {"AAPL", "MSFT"}

    def test_has_true(self, store: ArcticStore):
        store.write("AAPL", _df())
        assert store.has("AAPL") is True

    def test_has_false(self, store: ArcticStore):
        assert store.has("NONEXIST") is False

    def test_has_no_library(self, tmp_uri):
        """A fresh store with no library yet should return False, not raise."""
        s = ArcticStore(uri=tmp_uri, library="nonexistent")
        assert s.has("X") is False

    def test_delete(self, store: ArcticStore):
        store.write("AAPL", _df())
        store.delete("AAPL")
        assert store.has("AAPL") is False

    def test_read_metadata(self, store: ArcticStore):
        store.write("AAPL", _df(), metadata={"source": "test"})
        meta = store.read_metadata("AAPL")
        assert meta["source"] == "test"


class TestWriteRecords:
    def test_list_of_dicts(self, store: ArcticStore):
        data = [
            {"date": "2026-01-01", "value": 10},
            {"date": "2026-01-02", "value": 20},
        ]
        store.write("GDP", data)
        df = store.read("GDP", output="dataframe")
        assert len(df) == 2
        assert list(df.columns) == ["value"]
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_empty_raises(self, store: ArcticStore):
        with pytest.raises(ValueError, match="No data"):
            store.write("EMPTY", pd.DataFrame())
