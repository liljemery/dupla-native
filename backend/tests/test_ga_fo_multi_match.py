"""GA-FO multi-match: reglas y merge en pliego."""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.project import Project
from app.models.project_file import ProjectFile
from app.services.pliego_ga_fo_file_classifier import rule_based_ga_fo_matches
from app.services.project_file_classification_service import (
    _merge_ga_fo_items_complete,
    _run_ga_fo_autofill_from_upload,
)


def test_rule_based_arq_dwg_matches_multiple_section3_items() -> None:
    matches = rule_based_ga_fo_matches(
        original_name="LAS NASAS Plans ARQ Nov 21.dwg",
        discipline="arquitectura",
    )
    ids = {row[0] for row in matches}
    assert len(ids) >= 2
    assert any(iid.startswith("3.") for iid in ids)


@pytest.mark.asyncio
async def test_merge_ga_fo_items_complete_fills_all_pending(tmp_path) -> None:
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()
    pf = ProjectFile(
        id=file_id,
        project_id=project_id,
        storage_key=str(tmp_path / "plan.dwg"),
        original_name="plan arquitectura.dwg",
        discipline="arquitectura",
        created_at=datetime.utcnow(),
    )
    project = Project(
        id=project_id,
        name="Test",
        specifications_document={"ga_fo_01_arquitectura": {"item_states": {}}},
    )

    class Session:
        pass

    filled = await _merge_ga_fo_items_complete(Session(), project, pf, ["3.1.", "3.2.", "3.3."])
    assert filled == 3
    ga = project.specifications_document["ga_fo_01_arquitectura"]
    for iid in ("3.1.", "3.2.", "3.3."):
        row = ga["item_states"][iid]
        assert row["estado"] == "COMPLETO"
        assert row["file_uuid"] == str(file_id)


@pytest.mark.asyncio
async def test_run_ga_fo_autofill_applies_all_matches(tmp_path) -> None:
    path = tmp_path / "LAS NASAS Plans ARQ.dwg"
    path.write_bytes(b"AC1018")
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()
    pf = ProjectFile(
        id=file_id,
        project_id=project_id,
        storage_key=str(path),
        original_name="LAS NASAS Plans ARQ.dwg",
        discipline="arquitectura",
        mime="application/acad",
        created_at=datetime.utcnow(),
    )
    project = Project(
        id=project_id,
        name="Test",
        specifications_document={"ga_fo_01_arquitectura": {"item_states": {}}},
    )

    fake_matches = [("3.1.", 0.9, "test"), ("3.4.", 0.85, "test")]

    class Session:
        async def execute(self, stmt):
            class Result:
                def scalar_one_or_none(self_inner):
                    return project

            return Result()

    with patch("app.services.project_file_classification_service.get_settings") as gs, patch(
        "app.services.project_file_classification_service.classify_ga_fo_matches",
        new=AsyncMock(return_value=fake_matches),
    ), patch(
        "app.services.project_file_classification_service._fill_pending_ga_fo_from_project_files",
        new=AsyncMock(),
    ):
        gs.return_value.openai_api_key = "sk-test"
        gs.return_value.aps_client_id = ""
        await _run_ga_fo_autofill_from_upload(Session(), pf)

    ga = project.specifications_document["ga_fo_01_arquitectura"]
    assert ga["item_states"]["3.1."]["estado"] == "COMPLETO"
    assert ga["item_states"]["3.4."]["estado"] == "COMPLETO"
    assert pf.file_ingest_snapshot["ga_fo_multi_v1"] is True
    assert set(pf.file_ingest_snapshot["ga_fo_matched_items"]) == {"3.1.", "3.4."}
