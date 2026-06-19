"""Default profile resolution for coordination runs."""

from __future__ import annotations

import os

from wrapper.run_clash_analysis import (
    FAST_COMPARE_LOCAL_PROFILE,
    FAST_COMPARE_PROFILE,
    _resolve_analysis_profile,
)


def test_resolve_profile_prefers_local_on_non_windows(monkeypatch) -> None:
    monkeypatch.delenv("COORDINATION_ANALYSIS_PROFILE", raising=False)
    monkeypatch.setenv("CLIENT_ID", "x")
    monkeypatch.setenv("CLIENT_SECRET", "y")
    monkeypatch.setattr("wrapper.run_clash_analysis._accore_available", lambda: False)
    assert _resolve_analysis_profile() == FAST_COMPARE_LOCAL_PROFILE


def test_resolve_profile_uses_accore_when_available(monkeypatch) -> None:
    monkeypatch.delenv("COORDINATION_ANALYSIS_PROFILE", raising=False)
    monkeypatch.setattr("wrapper.run_clash_analysis._accore_available", lambda: True)
    assert _resolve_analysis_profile() == FAST_COMPARE_PROFILE


def test_resolve_profile_honors_override(monkeypatch) -> None:
    monkeypatch.setenv("COORDINATION_ANALYSIS_PROFILE", "fast_compare_local")
    assert _resolve_analysis_profile() == FAST_COMPARE_LOCAL_PROFILE
