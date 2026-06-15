from __future__ import annotations

import json
import sys
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def _artifacts(tmp_path: Path):
    from tasks import ExtractionArtifacts

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    page_path = pages_dir / "page_0001.png"
    page_path.write_bytes(b"")
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    return ExtractionArtifacts(
        artifact_key="artifact-key",
        artifact_dir=artifact_dir,
        raw_json_path=artifact_dir / "raw.json",
        normalized_json_path=artifact_dir / "normalized.json",
        pages_dir=pages_dir,
        page_paths=[page_path],
        raw_data=[],
        normalized={},
        manifest={},
        cache_hit=False,
    )


def test_poisoned_vision_artifact_is_unlinked_and_rebuilt(tmp_path, monkeypatch):
    import tasks

    artifacts = _artifacts(tmp_path)
    vision_path = tmp_path / "artifact" / "vision" / "arquitectura_poison.json"
    vision_path.parent.mkdir(parents=True)
    poisoned = [{"error": f"boom {idx}"} for idx in range(8)] + [{"walls": []}, {"walls": []}]
    vision_path.write_text(json.dumps(poisoned), encoding="utf-8")

    clean_payload = [{"walls": []}]
    calls = {"vision": 0}
    unlinked: list[Path] = []
    original_unlink = Path.unlink

    def tracking_unlink(self: Path, *args, **kwargs):
        if self == vision_path:
            unlinked.append(self)
        return original_unlink(self, *args, **kwargs)

    def fake_run_full_vision_analysis(*args, **kwargs):
        calls["vision"] += 1
        return clean_payload

    monkeypatch.delenv("DUPLA_SKIP_VISION", raising=False)
    monkeypatch.setattr(tasks, "_vision_artifact_path", lambda *args, **kwargs: vision_path)
    monkeypatch.setattr(tasks, "run_full_vision_analysis", fake_run_full_vision_analysis)
    monkeypatch.setattr(Path, "unlink", tracking_unlink)

    result = tasks._load_or_build_vision_results(
        artifacts=artifacts,
        normalized={},
        discipline_id="arquitectura",
        methodology=None,
    )

    assert result == clean_payload
    assert calls["vision"] == 1
    assert unlinked == [vision_path]
    assert json.loads(vision_path.read_text(encoding="utf-8")) == clean_payload


def test_poisoned_vision_result_is_not_written(tmp_path, monkeypatch):
    import tasks

    artifacts = _artifacts(tmp_path)
    vision_path = tmp_path / "artifact" / "vision" / "arquitectura_poison.json"
    poisoned = [{"error": f"boom {idx}"} for idx in range(8)] + [{"walls": []}, {"walls": []}]

    monkeypatch.delenv("DUPLA_SKIP_VISION", raising=False)
    monkeypatch.setattr(tasks, "_vision_artifact_path", lambda *args, **kwargs: vision_path)
    monkeypatch.setattr(tasks, "run_full_vision_analysis", lambda *args, **kwargs: poisoned)

    result = tasks._load_or_build_vision_results(
        artifacts=artifacts,
        normalized={},
        discipline_id="arquitectura",
        methodology=None,
    )

    assert result == poisoned
    assert not vision_path.exists()
