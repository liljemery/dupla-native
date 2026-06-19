"""Classification task integration tests."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.file_discipline import FileDiscipline
from app.models.project_file import ProjectFile
from app.services.motor_discipline_types import MotorDisciplineInference
from app.services.project_file_classification_service import (
    _apply_motor_discipline_from_content,
    run_file_classification_task,
)


@pytest.mark.asyncio
async def test_apply_motor_sets_discipline_and_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "file.pdf"
    path.write_bytes(b"%PDF-1.4")
    pf = ProjectFile(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        storage_key=str(path),
        original_name="el-tablero.pdf",
        created_at=datetime.utcnow(),
    )
    inference = MotorDisciplineInference(
        discipline=FileDiscipline.ELECTRICA,
        method="pdf_text",
        confidence=0.82,
        snapshot={"discipline_method": "pdf_text", "confidence": 0.82},
        aps=None,
    )

    class Session:
        async def flush(self):
            return None

    with patch(
        "app.services.project_file_classification_service.infer_file_discipline_from_content",
        new=AsyncMock(return_value=inference),
    ), patch(
        "app.services.project_file_classification_service.folder_rel_posix_for_file",
        new=AsyncMock(return_value=None),
    ):
        await _apply_motor_discipline_from_content(Session(), pf)

    assert pf.discipline == "electrica"
    assert pf.file_ingest_snapshot["discipline_method"] == "pdf_text"


@pytest.mark.asyncio
async def test_apply_motor_skips_when_discipline_preset() -> None:
    pf = ProjectFile(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        storage_key="/tmp/x.pdf",
        original_name="x.pdf",
        discipline="estructura",
        created_at=datetime.utcnow(),
    )
    with patch(
        "app.services.project_file_classification_service.infer_file_discipline_from_content",
        new=AsyncMock(),
    ) as mocked:
        await _apply_motor_discipline_from_content(object(), pf)
    mocked.assert_not_called()


@pytest.mark.asyncio
async def test_apply_motor_uses_project_sibling_when_inconclusive(tmp_path: Path) -> None:
    path = tmp_path / "Las Nasas 09 Rev 1.dwg"
    path.write_bytes(b"AC1018")
    project_id = uuid.uuid4()
    sibling = ProjectFile(
        id=uuid.uuid4(),
        project_id=project_id,
        storage_key=str(tmp_path / "other.dwg"),
        original_name="LAS NASAS Plans ARQ Nov 21.dwg",
        discipline="arquitectura",
        ingest_status="PUBLISHED",
        created_at=datetime.utcnow(),
    )
    pf = ProjectFile(
        id=uuid.uuid4(),
        project_id=project_id,
        storage_key=str(path),
        original_name="Las Nasas 09 Rev 1.dwg",
        ingest_status="PUBLISHED",
        created_at=datetime.utcnow(),
    )
    inference = MotorDisciplineInference(
        discipline=None,
        method="inconclusive",
        confidence=0.0,
        snapshot={"discipline_method": "inconclusive", "confidence": 0.0},
        aps=None,
    )

    class Session:
        async def execute(self, _stmt):
            class Result:
                def first(self_inner):
                    return ("arquitectura", 1)

            return Result()

        async def flush(self):
            return None

    with patch(
        "app.services.project_file_classification_service.infer_file_discipline_from_content",
        new=AsyncMock(return_value=inference),
    ), patch(
        "app.services.project_file_classification_service.folder_rel_posix_for_file",
        new=AsyncMock(return_value=None),
    ):
        await _apply_motor_discipline_from_content(Session(), pf)

    assert pf.discipline == "arquitectura"
    assert pf.file_ingest_snapshot.get("project_sibling_hint") is True


@pytest.mark.asyncio
async def test_apply_motor_uses_filename_fallback_when_inconclusive(tmp_path: Path) -> None:
    path = tmp_path / "LAS NASAS Plans ARQ Nov 21.dwg"
    path.write_bytes(b"AC1018")
    pf = ProjectFile(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        storage_key=str(path),
        original_name="LAS NASAS Plans ARQ Nov 21.dwg",
        created_at=datetime.utcnow(),
    )
    inference = MotorDisciplineInference(
        discipline=None,
        method="inconclusive",
        confidence=0.0,
        snapshot={"discipline_method": "inconclusive", "confidence": 0.0, "classified_at": "2026-01-01T00:00:00Z"},
        aps=None,
    )

    class Session:
        async def flush(self):
            return None

    with patch(
        "app.services.project_file_classification_service.infer_file_discipline_from_content",
        new=AsyncMock(return_value=inference),
    ), patch(
        "app.services.project_file_classification_service.folder_rel_posix_for_file",
        new=AsyncMock(return_value=None),
    ):
        await _apply_motor_discipline_from_content(Session(), pf)

    assert pf.discipline == "arquitectura"
    assert pf.file_ingest_snapshot.get("filename_fallback") is True


@pytest.mark.asyncio
async def test_run_classification_task_commits(tmp_path: Path) -> None:
    path = tmp_path / "plan.pdf"
    path.write_bytes(b"%PDF-1.4")
    file_id = uuid.uuid4()
    pf = ProjectFile(
        id=file_id,
        project_id=uuid.uuid4(),
        storage_key=str(path),
        original_name="plan.pdf",
        ingest_status="PUBLISHED",
        created_at=datetime.utcnow(),
    )

    session = MagicMock()
    session.get = AsyncMock(return_value=pf)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    inference = MotorDisciplineInference(
        discipline=None,
        method="inconclusive",
        confidence=0.0,
        snapshot={"discipline_method": "inconclusive", "confidence": 0.0},
        aps=None,
    )

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.services.project_file_classification_service.infer_file_discipline_from_content",
        new=AsyncMock(return_value=inference),
    ), patch(
        "app.services.project_file_classification_service._run_ga_fo_autofill_from_upload",
        new=AsyncMock(),
    ), patch(
        "app.services.project_file_classification_service.resolve_discipline_folder_id",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.services.project_file_classification_service.AsyncSessionLocal",
        return_value=cm,
    ):
        await run_file_classification_task(file_id)

    session.commit.assert_awaited()
    assert session.commit.await_count == 2
    assert pf.file_ingest_snapshot is not None
