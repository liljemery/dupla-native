"""Motor subprocess adapter tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.domain.file_discipline import FileDiscipline
from app.services.motor_discipline_types import MotorDisciplineInference
from app.services.motor_file_discipline import (
    _map_bucket_to_file_discipline,
    infer_file_discipline_from_content,
)


def test_map_bucket_to_file_discipline() -> None:
    assert _map_bucket_to_file_discipline("electrica") == FileDiscipline.ELECTRICA
    assert _map_bucket_to_file_discipline("sin_clasificar") is None


@pytest.mark.asyncio
async def test_infer_subprocess_parses_json(tmp_path: Path) -> None:
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"pdf")
    payload = {
        "discipline": "electrica",
        "method": "pdf_text",
        "confidence": 0.9,
        "snapshot": {"cad_cache_key": "abc", "discipline_method": "pdf_text"},
        "aps": None,
    }

    with patch(
        "app.services.motor_file_discipline._run_infer_subprocess",
        return_value=payload,
    ):
        result = await infer_file_discipline_from_content(
            storage_path=sample,
            rel_posix=None,
            object_key=None,
        )

    assert isinstance(result, MotorDisciplineInference)
    assert result.discipline == FileDiscipline.ELECTRICA
    assert result.snapshot["cad_cache_key"] == "abc"


def test_subprocess_stdout_last_line_json(tmp_path: Path) -> None:
    payload = {"discipline": "estructura", "confidence": 0.8, "snapshot": {}, "aps": None}
    line = json.dumps(payload)
    parsed = json.loads(line.strip().splitlines()[-1])
    assert parsed["discipline"] == "estructura"
