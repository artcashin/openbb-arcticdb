# openbb-arcticdb

[ArcticDB](https://arcticdb.io) integration for the OpenBB Platform — **both
directions**:

- **Write** — persist any OBBject result to an ArcticDB library:
  ```python
  res = obb.equity.price.historical("AAPL", provider="yfinance")
  res.arcticdb.write("AAPL")                       # -> default library
  res.arcticdb.write("AAPL", library="prices", metadata={"src": "yfinance"})
  res.arcticdb.append("AAPL")                      # append new rows
  res.arcticdb.list_symbols(library="prices")
  ```
- **Read (OHLCV)** — serve stored bars back through the normal OpenBB interface
  for **equity, ETF, crypto, currency, and index** historical:
  ```python
  obb.equity.price.historical("AAPL", provider="arcticdb")
  obb.crypto.price.historical("BTCUSD", provider="arcticdb", start_date="2026-01-01")
  ```
- **Tick → OHLCV on read** — pass `interval` to resample a stored tick symbol
  (a `price` column + optional `size`/`volume`) into OHLCV bars. ArcticDB filters
  by `date_range` on the server; the resample itself is done client-side with
  pandas.
  ```python
  obb.equity.price.historical("XYZ", provider="arcticdb", library="ticks",
                              interval="1m", start_date="2026-06-01", end_date="2026-06-02")
  ```
  Supported intervals (lowercase `m` = minute, per OpenBB):
  `1s`, `1m`/`5m`/`15m`/`30m`, `1h`/`4h`, `1d`, `1w`/`2w`, `1mo`/`3mo` (also `1M`/`3M`).
  Both `start_date` and `end_date` accept **date or datetime** (a date `end` is
  inclusive of the whole day; a datetime is exact).
  **No `interval` → defaults to `1d`** (this also covers `interval="1d"`, which
  OpenBB silently strips because `1d` is its global default). For raw, non-OHLCV
  rows use `store.read("XYZ", library="ticks")`.
- **`pandas_anchor`** (bool, default `False`) — bucket anchoring. `False`
  (default) uses ArcticDB's epoch anchor; `True` uses the pandas default anchor
  (`origin='start_day'`). Mainly visible on intraday intervals that don't evenly divide a day
  (e.g. `5h`: start-of-day edges vs epoch edges). Implemented as a midnight
  Timestamp origin because ArcticDB rejects the `start_day` string alongside a
  `date_range`.
- **Generic read/write (any data)** — for non-OHLCV data (economy series,
  fundamentals, screeners, arbitrary DataFrames), use the `store` API:
  ```python
  from openbb_arcticdb import store
  s = store(library="research")            # uri/library default to env/LMDB
  s.write("gdp", obb.economy.gdp.real(provider="oecd"))   # OBBject, DataFrame, or records
  s.write("notes", my_dataframe, metadata={"src": "manual"})
  obj = s.read("gdp")                       # OBBject (default): .to_df(), charting, ...
  df  = s.read("gdp", output="dataframe", start_date="2026-01-01", columns=["value"])
  s.list_symbols(); s.has("gdp"); s.read_metadata("gdp"); s.delete("gdp"); s.append("gdp", more)
  ```

The round-trip lets you pull once from a live provider, store it, then re-read
offline with no API calls or rate limits — versioned and time-travel capable.

The `.arcticdb` accessor (on any OBBject) mirrors the write side:
`res.arcticdb.write/append/list_symbols/read_metadata/delete(...)`.

## Configuration

No OpenBB credentials are required. The connection is resolved with this
precedence: **per-call query param > `ARCTICDB_URI`/`ARCTICDB_LIBRARY` env vars >
default**.

- `ARCTICDB_URI`     — e.g. `lmdb:///root/.openbb_platform/arcticdb` (local file
  store, default) or `s3://endpoint:bucket?...` / `azure://...`
- `ARCTICDB_LIBRARY` — defaults to `openbb`

The default LMDB store lives under `OPENBB_HOME`, so in the container it sits on
the persistent `openbb-data` volume automatically.

## Supported

- Provider read path: `EquityHistorical`, `EtfHistorical`, `CryptoHistorical`,
  `CurrencyHistorical`, `IndexHistorical` (OHLCV standard models), with an
  `interval` param that resamples stored tick/fine data into OHLCV on read
- Generic `store` API: `write`, `append`, `read` (OBBject or DataFrame, with
  `start_date`/`end_date`/`columns`), `list_symbols`, `has`, `delete`,
  `read_metadata` — for any data shape
- `.arcticdb` OBBject accessor: `write`, `append`, `list_symbols`,
  `read_metadata`, `delete`

## Note

The package registers the name `arcticdb` as both a provider and an OBBject
accessor (intentional). OpenBB emits a harmless one-line warning
("Skipping 'arcticdb', name already in user.") when credentials are first
loaded; it does not affect functionality.
