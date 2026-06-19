"""Tests for hybrid geometry quality audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

MOTOR_ROOT = Path(__file__).resolve().parents[1]
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

from coordination.extraction.hybrid_geometry_audit import (
    audit_hybrid_geometry_manifest,
    audit_hybrid_geometry_manifest_file,
    render_hybrid_geometry_audit_markdown,
)


def _manifest() -> dict:
    return {
        "results": [
            {
                "source": {
                    "label": "arq",
                    "discipline": "ARQUITECTURA",
                    "file_name": "ARQ.dwg",
                },
                "alignment_summary": {
                    "A-1.1": {
                        "status": "ok",
                        "n_pairs": 100,
                        "n_inliers": 95,
                        "n_outliers": 5,
                        "rms_error_sheet": 0.1,
                        "max_error_sheet": 0.2,
                    }
                },
                "hybrid_summary": {
                    "record_count": 100,
                    "source_counts": {"dxf_ezdxf_transformed": 90, "aps_fragment_fallback": 10},
                    "quality_counts": {"good": 95, "coarse": 5},
                    "view_source_counts": {
                        "A-1.1": {"dxf_ezdxf_transformed": 90, "aps_fragment_fallback": 10},
                    },
                },
            }
        ]
    }


def test_audit_hybrid_geometry_manifest_returns_ok_for_clean_run() -> None:
    audit = audit_hybrid_geometry_manifest(_manifest())

    assert audit["schema_version"] == "hybrid_geometry_audit.v1"
    assert audit["status"] == "ok"
    assert audit["summary"]["views_ok"] == 1
    assert audit["summary"]["issues_fail"] == 0
    assert audit["issues"] == []


def test_audit_hybrid_geometry_manifest_flags_insufficient_alignment() -> None:
    manifest = _manifest()
    manifest["results"][0]["alignment_summary"]["A-1.5.1"] = {
        "status": "insufficient",
        "n_pairs": 2,
        "n_inliers": 0,
        "n_outliers": 0,
        "rms_error_sheet": None,
        "max_error_sheet": None,
    }

    audit = audit_hybrid_geometry_manifest(manifest)

    assert audit["status"] == "fail"
    assert audit["summary"]["views_fail"] == 1
    assert any(issue["code"] == "alignment_insufficient" for issue in audit["issues"])


def test_audit_hybrid_geometry_manifest_flags_high_outlier_and_fallback_ratios() -> None:
    manifest = _manifest()
    result = manifest["results"][0]
    result["alignment_summary"]["A-1.1"] = {
        "status": "ok",
        "n_pairs": 100,
        "n_inliers": 10,
        "n_outliers": 90,
        "rms_error_sheet": 0.2,
        "max_error_sheet": 0.3,
    }
    result["hybrid_summary"] = {
        "record_count": 100,
        "source_counts": {"dxf_ezdxf_transformed": 15, "aps_fragment_fallback": 85},
        "quality_counts": {"good": 30, "coarse": 70},
    }

    audit = audit_hybrid_geometry_manifest(manifest)

    assert audit["status"] == "fail"
    codes = {issue["code"] for issue in audit["issues"]}
    assert "alignment_high_outlier_ratio" in codes
    assert "hybrid_high_fallback_ratio" in codes
    assert "hybrid_high_coarse_ratio" in codes


def test_audit_hybrid_geometry_manifest_file_writes_output(tmp_path: Path) -> None:
    manifest_path = tmp_path / "hybrid_geometry_manifest.json"
    audit_path = tmp_path / "hybrid_geometry_audit.json"
    audit_md_path = tmp_path / "hybrid_geometry_audit.md"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")

    audit = audit_hybrid_geometry_manifest_file(
        manifest_path,
        output_path=audit_path,
        markdown_output_path=audit_md_path,
    )

    assert audit["status"] == "ok"
    assert audit["manifest_path"] == str(manifest_path)
    assert json.loads(audit_path.read_text(encoding="utf-8"))["status"] == "ok"
    assert "# Hybrid Geometry Audit" in audit_md_path.read_text(encoding="utf-8")


def test_audit_hybrid_geometry_manifest_flags_fallback_only_view_as_warn() -> None:
    """Views with APS fallback records and NO alignment data must be flagged."""
    manifest = _manifest()
    result = manifest["results"][0]
    result["hybrid_summary"]["view_source_counts"]["A-1.2"] = {"aps_fragment_fallback": 10}
    result["hybrid_summary"]["record_count"] = 110
    result["hybrid_summary"]["source_counts"]["aps_fragment_fallback"] = 20

    audit = audit_hybrid_geometry_manifest(manifest)

    codes = {issue["code"] for issue in audit["issues"]}
    assert "fallback_only_view" in codes
    fallback_issues = [i for i in audit["issues"] if i["code"] == "fallback_only_view"]
    assert fallback_issues[0]["view"] == "A-1.2"
    assert fallback_issues[0]["severity"] in {"warn", "fail"}
    assert audit["summary"]["views_warn"] + audit["summary"]["views_fail"] >= 1


def test_audit_hybrid_geometry_manifest_fallback_only_view_fail_when_dominant() -> None:
    """Fallback-only view becomes fail when its records exceed fail_fallback_ratio of total."""
    manifest = _manifest()
    result = manifest["results"][0]
    result["hybrid_summary"]["view_source_counts"]["A-1.2"] = {"aps_fragment_fallback": 90}
    result["hybrid_summary"]["record_count"] = 100
    result["hybrid_summary"]["source_counts"] = {
        "dxf_ezdxf_transformed": 10,
        "aps_fragment_fallback": 90,
    }

    audit = audit_hybrid_geometry_manifest(manifest)

    fallback_issues = [i for i in audit["issues"] if i["code"] == "fallback_only_view"]
    assert fallback_issues, "Expected fallback_only_view issue"
    assert fallback_issues[0]["severity"] == "fail"


def test_audit_hybrid_geometry_manifest_no_false_positive_for_aligned_views() -> None:
    """Views present in alignment_summary must NOT trigger fallback_only_view even if they have fallback records."""
    audit = audit_hybrid_geometry_manifest(_manifest())

    codes = {issue["code"] for issue in audit["issues"]}
    assert "fallback_only_view" not in codes


def test_render_hybrid_geometry_audit_markdown_includes_issues() -> None:
    manifest = _manifest()
    manifest["results"][0]["alignment_summary"]["A-1.5.1"] = {
        "status": "insufficient",
        "n_pairs": 2,
        "n_inliers": 0,
        "n_outliers": 0,
        "rms_error_sheet": None,
        "max_error_sheet": None,
    }

    markdown = render_hybrid_geometry_audit_markdown(audit_hybrid_geometry_manifest(manifest))

    assert "Status: `FAIL`" in markdown
    assert "| arq | A-1.5.1 | `fail` |" in markdown
    assert "`alignment_insufficient`" in markdown
