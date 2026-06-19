"""Processor CAD staging name helpers."""

from __future__ import annotations

from tasks import _safe_upload_name


def test_safe_upload_name_hash_prefix() -> None:
    name = _safe_upload_name("plan.dwg", "upload_0.dwg", content_hash="abcdef0123456789")
    assert name == "abcdef01_plan.dwg"


def test_safe_upload_name_strips_path() -> None:
    name = _safe_upload_name("../../nested/plan.dwg", "upload_0.dwg")
    assert name == "plan.dwg"
