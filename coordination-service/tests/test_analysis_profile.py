import os
from unittest.mock import patch

from wrapper.run_clash_analysis import (
    FAST_COMPARE_APS_PROFILE,
    FAST_COMPARE_PROFILE,
    _resolve_analysis_profile,
)


def test_resolve_profile_prefers_aps_on_any_os(monkeypatch) -> None:
    monkeypatch.delenv("COORDINATION_ANALYSIS_PROFILE", raising=False)
    monkeypatch.setenv("CLIENT_ID", "id")
    monkeypatch.setenv("CLIENT_SECRET", "secret")
    with patch("wrapper.run_clash_analysis._accore_available", return_value=True):
        assert _resolve_analysis_profile() == FAST_COMPARE_APS_PROFILE


def test_resolve_profile_windows_accore_without_aps(monkeypatch) -> None:
    monkeypatch.delenv("COORDINATION_ANALYSIS_PROFILE", raising=False)
    monkeypatch.delenv("CLIENT_ID", raising=False)
    monkeypatch.delenv("CLIENT_SECRET", raising=False)
    with patch("wrapper.run_clash_analysis._accore_available", return_value=True):
        assert _resolve_analysis_profile() == FAST_COMPARE_PROFILE


def test_resolve_profile_env_override(monkeypatch) -> None:
    monkeypatch.setenv("COORDINATION_ANALYSIS_PROFILE", "standard")
    assert _resolve_analysis_profile() == "standard"
