"""ArcticDB integration for OpenBB (provider + OBBject accessor + generic store)."""

from openbb_core.app.model.extension import Extension
from openbb_core.provider.abstract.provider import Provider

from openbb_arcticdb.accessor import ArcticDBAccessor
from openbb_arcticdb.models.historical import (
    ArcticDBCryptoHistoricalFetcher,
    ArcticDBCurrencyHistoricalFetcher,
    ArcticDBEquityHistoricalFetcher,
    ArcticDBEtfHistoricalFetcher,
    ArcticDBIndexHistoricalFetcher,
)
from openbb_arcticdb.store import ArcticStore, store

__all__ = ["arcticdb_provider", "ext", "ArcticStore", "store"]

# --- Read path: provider extension (OHLCV standard models) -----------------
arcticdb_provider = Provider(
    name="arcticdb",
    website="https://arcticdb.io",
    description=(
        "Serve bars stored in an ArcticDB library through the standard OpenBB "
        "interface (equity/etf/crypto/currency/index historical). Pair with the "
        "`.arcticdb` OBBject accessor and the `openbb_arcticdb.store` API to "
        "persist and read back ANY data offline."
    ),
    # No credentials: connection (URI/library) is configured via ARCTICDB_URI /
    # ARCTICDB_LIBRARY env vars or per-call query params (declaring credentials
    # would make them mandatory).
    credentials=None,
    fetcher_dict={
        "EquityHistorical": ArcticDBEquityHistoricalFetcher,
        "EtfHistorical": ArcticDBEtfHistoricalFetcher,
        "CryptoHistorical": ArcticDBCryptoHistoricalFetcher,
        "CurrencyHistorical": ArcticDBCurrencyHistoricalFetcher,
        "IndexHistorical": ArcticDBIndexHistoricalFetcher,
    },
    repr_name="ArcticDB",
)

# --- Write path: OBBject accessor ------------------------------------------
ext = Extension(
    name="arcticdb",
    description="Persist OBBject results to an ArcticDB library.",
)
ArcticDB = ext.obbject_accessor(ArcticDBAccessor)
