from __future__ import annotations

from datetime import datetime, timezone

from app.domain.management_approval_review import (
    parse_management_approval_entered_at,
    stamp_management_approval_entered,
)


def test_parse_management_approval_entered_at_iso():
    dt = parse_management_approval_entered_at(
        {"management_approval_entered_at": "2026-06-01T12:00:00+00:00"},
    )
    assert dt is not None
    assert dt.year == 2026


def test_stamp_management_approval_entered():
    meta = stamp_management_approval_entered({})
    assert isinstance(meta.get("management_approval_entered_at"), str)
    parsed = parse_management_approval_entered_at(meta)
    assert parsed is not None
    assert parsed <= datetime.now(timezone.utc)
