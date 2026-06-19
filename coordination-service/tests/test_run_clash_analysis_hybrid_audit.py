"""Wrapper contract tests for hybrid geometry audit artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

COORD_ROOT = Path(__file__).resolve().parents[1]
if str(COORD_ROOT) not in sys.path:
    sys.path.insert(0, str(COORD_ROOT))

from wrapper import run_clash_analysis as wrapper


def test_run_clash_analysis_exposes_hybrid_geometry_audit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COORDINATION_SMOKE_MODE", "false")
    monkeypatch.delenv("COORDINATION_HYBRID_GEOMETRY_AUDIT_GATE", raising=False)

    def fake_invoke_runner(*, inputs_dir: Path, registry_path: Path, output_dir: Path, include_disciplines=None) -> int:
        (output_dir / "clash_project_report.json").write_text(
            json.dumps(
                {
                    "project_name": "Demo",
                    "generated_at": "2026-06-18T00:00:00Z",
                    "conflict_count": 0,
                    "conflicts": [],
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "coordination_report_context.json").write_text(
            json.dumps({"project_name": "Demo", "counts": {"scheduled_pairs": 0}}),
            encoding="utf-8",
        )
        (output_dir / "pair_schedule.json").write_text(json.dumps({"pairs": []}), encoding="utf-8")
        return 0

    def fake_build_hybrid_geometry_artifacts(*, inputs_dir: Path, output_dir: Path, staged_files: list[dict]):
        hybrid_dir = output_dir / "hybrid_geometry"
        hybrid_dir.mkdir(parents=True, exist_ok=True)
        plan_path = hybrid_dir / "plan_geometry.hybrid.json"
        manifest_path = hybrid_dir / "hybrid_geometry_manifest.json"
        audit_path = hybrid_dir / "hybrid_geometry_audit.json"
        audit_md_path = hybrid_dir / "hybrid_geometry_audit.md"
        plan_path.write_text(
            json.dumps(
                {
                    "schema_version": "hybrid_plan_geometry.v1",
                    "coordinate_unit": "sheet_paper_units",
                    "files": {"ARQ.dxf": {"element_count": 12}},
                }
            ),
            encoding="utf-8",
        )
        manifest_path.write_text(json.dumps({"results": []}), encoding="utf-8")
        audit_path.write_text(
            json.dumps(
                {
                    "schema_version": "hybrid_geometry_audit.v1",
                    "status": "warn",
                    "summary": {"views_warn": 1, "issues_warn": 1},
                }
            ),
            encoding="utf-8",
        )
        audit_md_path.write_text("# Hybrid Geometry Audit\n", encoding="utf-8")
        return {
            "plan_geometry_path": str(plan_path),
            "manifest_path": str(manifest_path),
            "audit_path": str(audit_path),
            "audit_markdown_path": str(audit_md_path),
            "audit": {"status": "warn", "summary": {"views_warn": 1, "issues_warn": 1}},
            "results": [],
        }

    monkeypatch.setattr(wrapper, "_invoke_runner", fake_invoke_runner)
    monkeypatch.setattr(wrapper, "_build_hybrid_geometry_artifacts", fake_build_hybrid_geometry_artifacts)

    result = wrapper.run_clash_analysis(
        file_entries=[
            {
                "original_name": "ARQ.dxf",
                "discipline_bucket": "arquitectura",
                "content": b"0\nEOF\n",
            }
        ],
        profile_slug="folder",
        project_name="Demo",
        output_dir=tmp_path,
    )

    artifacts = result["artifacts"]
    assert artifacts["plan_geometry_hybrid"].endswith("plan_geometry.hybrid.json")
    assert artifacts["hybrid_geometry_manifest"].endswith("hybrid_geometry_manifest.json")
    assert artifacts["hybrid_geometry_audit"].endswith("hybrid_geometry_audit.json")
    assert artifacts["hybrid_geometry_audit_md"].endswith("hybrid_geometry_audit.md")
    assert artifacts["hybrid_geometry_audit_status"] == "warn"
    assert json.loads(artifacts["hybrid_geometry_audit_gate"]) == {
        "mode": "report_only",
        "status": "warn",
        "blocked": False,
    }

    context = json.loads(artifacts["coordination_context"])
    assert context["hybrid_geometry"]["audit"]["status"] == "warn"
    assert context["hybrid_geometry_audit_gate"]["mode"] == "report_only"
    assert result["report"]["geometry_audit"] == {
        "status": "warn",
        "summary": {"views_warn": 1, "issues_warn": 1},
        "gate": {"mode": "report_only", "status": "warn", "blocked": False},
    }
    analyzed_documents = result["report"]["analyzed_documents"]
    assert analyzed_documents[0]["element_count"] == 12


def test_hybrid_geometry_audit_gate_blocks_fail_status(monkeypatch) -> None:
    monkeypatch.setenv("COORDINATION_HYBRID_GEOMETRY_AUDIT_GATE", "fail")

    try:
        wrapper._hybrid_geometry_audit_gate({"audit": {"status": "fail"}})
    except RuntimeError as exc:
        assert "mode=fail, status=fail" in str(exc)
    else:
        raise AssertionError("expected hybrid geometry audit gate to block fail status")


def test_hybrid_geometry_audit_gate_blocks_missing_status(monkeypatch) -> None:
    monkeypatch.setenv("COORDINATION_HYBRID_GEOMETRY_AUDIT_GATE", "fail")

    try:
        wrapper._hybrid_geometry_audit_gate(None)
    except RuntimeError as exc:
        assert "mode=fail, status=missing" in str(exc)
    else:
        raise AssertionError("expected hybrid geometry audit gate to block missing status")


def test_hybrid_geometry_audit_gate_strict_blocks_warn_status(monkeypatch) -> None:
    monkeypatch.setenv("COORDINATION_HYBRID_GEOMETRY_AUDIT_GATE", "strict")

    try:
        wrapper._hybrid_geometry_audit_gate({"audit": {"status": "warn"}})
    except RuntimeError as exc:
        assert "mode=strict, status=warn" in str(exc)
    else:
        raise AssertionError("expected hybrid geometry audit gate to block warn status")


def test_build_hybrid_geometry_artifacts_converts_dwg_when_no_dxf_sources(monkeypatch, tmp_path: Path) -> None:
    inputs_dir = tmp_path / "inputs"
    cache_dir = tmp_path / "cache"
    output_dir = tmp_path / "out"
    inputs_dir.mkdir()
    cache_dir.mkdir(parents=True)
    output_dir.mkdir()
    (inputs_dir / "ARQ.dwg").write_bytes(b"dwg")
    converter = tmp_path / "ODAFileConverter"
    converter.write_text("#!/bin/sh\n", encoding="utf-8")

    calls: dict[str, object] = {}

    def fake_discover_hybrid_sources(*, inputs_dir: Path, cache_dir: Path, discipline_for_path=None):
        calls.setdefault("discover_inputs", []).append(Path(inputs_dir))
        if Path(inputs_dir).name == "dxf_inputs":
            return ["source"]
        return []

    class FakeBundle:
        results = [object()]
        plan_geometry_path = output_dir / "hybrid_geometry" / "plan_geometry.hybrid.json"

        def to_dict(self):
            return {"audit": {"status": "ok"}, "results": []}

    def fake_build_hybrid_artifacts(sources, out_dir):
        calls["sources"] = sources
        calls["out_dir"] = out_dir
        return FakeBundle()

    def fake_run(cmd, capture_output, text, timeout):
        calls["cmd"] = cmd
        dxf_dir = Path(cmd[2])
        dxf_dir.mkdir(parents=True, exist_ok=True)
        (dxf_dir / "ARQ.dxf").write_text("0\nEOF\n", encoding="utf-8")

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return Proc()

    monkeypatch.setenv("ODA_FILE_CONVERTER", str(converter))
    monkeypatch.setattr(wrapper.subprocess, "run", fake_run)
    monkeypatch.setitem(sys.modules, "coordination.extraction.hybrid_orchestrator", type("M", (), {
        "build_hybrid_artifacts": staticmethod(fake_build_hybrid_artifacts),
        "discover_hybrid_sources": staticmethod(fake_discover_hybrid_sources),
    }))

    summary = wrapper._build_hybrid_geometry_artifacts(
        inputs_dir=inputs_dir,
        output_dir=output_dir,
        staged_files=[{"path": str(inputs_dir / "ARQ.dwg"), "discipline_bucket": "arquitectura"}],
    )

    assert summary == {"audit": {"status": "ok"}, "results": []}
    assert calls["sources"] == ["source"]
    assert Path(calls["cmd"][1]) == inputs_dir
    assert Path(calls["cmd"][2]).name == "dxf_inputs"
