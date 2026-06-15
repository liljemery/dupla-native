"""Tests for stage_cache safe on-disk filename layout.

Any cache key, regardless of length or content, must produce a filesystem-safe
basename (sha256 hex + ".json", 69 chars). Round-trip via cache_set/cache_get
must still return the original value.
"""

from __future__ import annotations

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
    from core import stage_cache
    stage_cache.reset_stats()
    yield tmp_path
    stage_cache.reset_stats()


def test_long_key_produces_bounded_filename_and_round_trips(cache_dir):
    from core.stage_cache import cache_set, cache_get

    long_key = "x" * 2000
    value = {"data": "ok", "n": 42}

    cache_set("safe_path_stage", long_key, value)

    matches = list((Path(cache_dir) / "safe_path_stage").rglob("*.json"))
    assert matches, "cache_set must persist a file under the stage directory"
    for path in matches:
        assert len(path.name) <= 80, f"filename too long: {path.name} ({len(path.name)} chars)"

    assert cache_get("safe_path_stage", long_key) == value


def test_filename_is_sha256_hex_digest(cache_dir):
    import hashlib

    from core.stage_cache import _disk_path, cache_set

    key = "any-key-shape-works-here:plus:colons:and/slashes"
    cache_set("safe_path_stage", key, {"v": 1})

    expected = hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json"
    path = _disk_path("safe_path_stage", key)
    assert path.name == expected
    assert path.exists()


def test_different_long_keys_do_not_collide(cache_dir):
    from core.stage_cache import cache_get, cache_set

    key_a = "a" * 2000
    key_b = "a" * 1999 + "b"

    cache_set("safe_path_stage", key_a, "value_a")
    cache_set("safe_path_stage", key_b, "value_b")

    assert cache_get("safe_path_stage", key_a) == "value_a"
    assert cache_get("safe_path_stage", key_b) == "value_b"
