"""Test fixtures: temporary LMDB ArcticDB instance per test."""

import tempfile

import pytest


@pytest.fixture
def tmp_uri():
    """Create a unique temporary LMDB directory, yield the URI, then clean the cache."""
    with tempfile.TemporaryDirectory() as d:
        uri = f"lmdb://{d}/arcticdb"
        yield uri
        from openbb_arcticdb.utils import _arctic_cache
        _arctic_cache.pop(uri, None)


@pytest.fixture
def store(tmp_uri):
    """Return an ArcticStore pointed at a fresh temporary LMDB."""
    from openbb_arcticdb.store import ArcticStore
    return ArcticStore(uri=tmp_uri, library="test")


@pytest.fixture
def lib(tmp_uri):
    """Return an ArcticDB library handle for direct manipulation."""
    from openbb_arcticdb.utils import get_library
    return get_library(tmp_uri, "test", create_if_missing=True)
