#!/usr/bin/env python3
"""Load N days of daily OHLCV into ArcticDB and verify the round-trip.

Downloads daily bars from yfinance and writes them to an ArcticDB library via
the openbb-arcticdb integration, then reads them back through both the generic
store and the `provider="arcticdb"` path.

Usage:
    python load_aapl.py [--symbol AAPL] [--days 30] [--library openbb] [--uri ...]

Env fallbacks: ARCTICDB_URI, ARCTICDB_LIBRARY (CLI args take precedence).
Defaults to a local LMDB store under OPENBB_HOME (no server needed).
"""
import argparse
import os
import sys
import warnings
from datetime import date, timedelta

warnings.filterwarnings("ignore")


def main() -> int:
    p = argparse.ArgumentParser(description="Load daily OHLCV into ArcticDB and verify.")
    p.add_argument("--symbol", default="AAPL")
    p.add_argument("--days", type=int, default=30, help="calendar days of history")
    p.add_argument("--library", default=os.getenv("ARCTICDB_LIBRARY", "openbb"))
    p.add_argument("--uri", default=os.getenv("ARCTICDB_URI"))  # None -> default LMDB
    args = p.parse_args()

    from openbb import obb
    from openbb_arcticdb import store

    start = (date.today() - timedelta(days=args.days)).isoformat()
    print(f"[1/4] Downloading {args.symbol} daily OHLCV since {start} (yfinance)...")
    src = obb.equity.price.historical(args.symbol, provider="yfinance", start_date=start)
    n = len(src.results)
    if n == 0:
        print("  ERROR: yfinance returned no rows.", file=sys.stderr)
        return 1
    print(f"  got {n} rows: {src.results[0].date} -> {src.results[-1].date}")

    print(f"[2/4] Writing to ArcticDB library '{args.library}'"
          + (f" @ {args.uri}" if args.uri else " (default LMDB)") + "...")
    info = src.arcticdb.write(args.symbol, library=args.library, uri=args.uri,
                              metadata={"source": "yfinance", "interval": "1d"})
    print(f"  {info}")

    print("[3/4] Reading back via the generic store...")
    s = store(uri=args.uri, library=args.library)
    df = s.read(args.symbol, output="dataframe")
    print(f"  store.read: {len(df)} rows, columns={list(df.columns)}")

    print("[4/4] Reading back via provider='arcticdb' (interval=1d)...")
    back = obb.equity.price.historical(
        args.symbol, provider="arcticdb", interval="1d",
        uri=args.uri, library=args.library,
    )
    print(f"  provider rows: {len(back.results)}, last close: {back.results[-1].close}")

    ok = len(df) == n and len(back.results) == n
    print(f"\n{'PASS' if ok else 'FAIL'}: wrote {n}, store read {len(df)}, "
          f"provider read {len(back.results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
