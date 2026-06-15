"""Tests for processor/core/stage_cache.py.

Disk-only mode (DUPLA_CACHE_BACKEND=disk) is forced so the suite does not
require a Redis instance to be running.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DUPLA_CACHE_BACKEND", "disk")
    monkeypatch.setenv("DUPLA_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("DUPLA_NO_CACHE", raising=False)
    monkeypatch.delenv("DUPLA_CACHE_DISABLE_WRITE", raising=False)
    # Reset module-level state between tests.
    from core import stage_cache
    stage_cache.reset_stats()
    yield tmp_path
    stage_cache.reset_stats()


def test_hash_helpers_are_deterministic():
    from core.stage_cache import sha256_bytes, sha256_json, compose_key
    assert sha256_bytes(b"abc") == sha256_bytes(b"abc")
    assert sha256_bytes(b"abc") != sha256_bytes(b"abd")
    assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})
    assert compose_key("x", "y", None, "z") == "x:y:z"


def test_cache_miss_then_hit(cache_dir):
    from core.stage_cache import cached_stage, get_stats

    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"value": 42}

    out1 = cached_stage("unit_test_stage", "abc123", compute)
    out2 = cached_stage("unit_test_stage", "abc123", compute)

    assert out1 == out2 == {"value": 42}
    assert calls["n"] == 1, "compute_fn must only run on miss"
    stats = get_stats()["unit_test_stage"]
    assert stats["misses"] == 1
    assert stats["hits"] == 1
    assert stats["writes"] == 1


def test_distinct_keys_compute_separately(cache_dir):
    from core.stage_cache import cached_stage

    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    a = cached_stage("unit_test_stage", "key_a", compute)
    b = cached_stage("unit_test_stage", "key_b", compute)
    assert a != b
    assert calls["n"] == 2


def test_bypass_flag_skips_cache(cache_dir, monkeypatch):
    from core.stage_cache import cached_stage

    monkeypatch.setenv("DUPLA_NO_CACHE", "1")
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    cached_stage("unit_test_stage", "k", compute)
    cached_stage("unit_test_stage", "k", compute)
    assert calls["n"] == 2, "bypass must always recompute"


def test_disable_write_skips_writes(cache_dir, monkeypatch):
    from core.stage_cache import cached_stage

    monkeypatch.setenv("DUPLA_CACHE_DISABLE_WRITE", "1")
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    cached_stage("unit_test_stage", "k", compute)
    cached_stage("unit_test_stage", "k", compute)
    # Both runs miss because the first never wrote.
    assert calls["n"] == 2


def test_invalidate_stage_clears_entries(cache_dir):
    from core.stage_cache import cached_stage, invalidate, get_stats

    cached_stage("unit_test_stage", "k1", lambda: "a")
    cached_stage("unit_test_stage", "k2", lambda: "b")
    removed = invalidate(stage="unit_test_stage")
    assert removed >= 2

    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return "c"

    cached_stage("unit_test_stage", "k1", compute)
    assert calls["n"] == 1, "invalidated entry must recompute"


def test_invalidate_single_key(cache_dir):
    from core.stage_cache import cached_stage, invalidate

    cached_stage("unit_test_stage", "k1", lambda: "a")
    cached_stage("unit_test_stage", "k2", lambda: "b")
    invalidate(stage="unit_test_stage", key="k1")

    a_calls = {"n": 0}

    def recompute_a():
        a_calls["n"] += 1
        return "a"

    b_calls = {"n": 0}

    def recompute_b():
        b_calls["n"] += 1
        return "b"

    cached_stage("unit_test_stage", "k1", recompute_a)
    cached_stage("unit_test_stage", "k2", recompute_b)
    assert a_calls["n"] == 1, "k1 should have been invalidated"
    assert b_calls["n"] == 0, "k2 must still be cached"


def test_persisted_to_disk(cache_dir):
    from core.stage_cache import cached_stage

    cached_stage("unit_test_stage", "persist_key", lambda: {"x": 1})
    # Filenames are sha256 hashes of the key, not the raw key — locate any
    # persisted JSON file under the stage directory.
    matches = list((Path(cache_dir) / "unit_test_stage").rglob("*.json"))
    assert matches, "cache entry must be persisted to disk"


def test_force_overrides_cache(cache_dir):
    from core.stage_cache import cached_stage

    cached_stage("unit_test_stage", "k", lambda: 1)
    result = cached_stage("unit_test_stage", "k", lambda: 99, force=True)
    assert result == 99
    # Subsequent read returns the overwritten value.
    assert cached_stage("unit_test_stage", "k", lambda: 0) == 99
