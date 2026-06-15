from __future__ import annotations

import asyncio
import sys
import time
from collections import Counter
from pathlib import Path

_PROCESSOR_ROOT = Path(__file__).resolve().parent.parent
if str(_PROCESSOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROCESSOR_ROOT))


def test_run_full_vision_analysis_respects_concurrency_and_rotates_keys(tmp_path, monkeypatch):
    from agents import vision_agent
    from core import api_key_manager

    api_key_manager._GLOBAL_COOLDOWNS.clear()
    monkeypatch.setenv("DUPLA_OPENAI_KEYS", "k1,k2,k3")
    monkeypatch.setenv("DUPLA_VISION_CONCURRENCY", "15")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    vision_agent._KEY_MANAGER = None

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    for index in range(30):
        (pages_dir / f"page_{index:04d}.png").write_bytes(b"")

    in_flight = 0
    max_in_flight = 0
    keys: list[str] = []
    per_call_latency = 0.10

    async def fake_analyze_plan_async(
        image_path: Path,
        cad_summary: dict,
        level_name: str,
        *,
        office_methodology: str | None = None,
        upload_discipline_id: str | None = None,
    ) -> dict:
        nonlocal in_flight, max_in_flight
        key = vision_agent._get_key_manager().next_key()
        keys.append(key)
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(per_call_latency)
        in_flight -= 1
        return {
            "level_id": level_name,
            "level_name": level_name,
            "source": "vision",
            "source_refs": [f"vision:{image_path.name}"],
            "walls": [],
        }

    monkeypatch.setattr(vision_agent, "analyze_plan_async", fake_analyze_plan_async)

    started = time.monotonic()
    results = vision_agent.run_full_vision_analysis(str(pages_dir), {})
    elapsed = time.monotonic() - started

    assert len(results) == 30
    assert max_in_flight <= 15
    assert elapsed <= (2 * per_call_latency) + 0.25

    counts = Counter(keys)
    assert set(counts) == {"k1", "k2", "k3"}
    assert max(counts.values()) - min(counts.values()) <= 2
