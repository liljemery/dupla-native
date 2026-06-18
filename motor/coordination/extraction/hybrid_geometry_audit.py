"""Quality audit for hybrid DXF/APS geometry artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SEVERITY_RANK = {"ok": 0, "warn": 1, "fail": 2}


@dataclass(frozen=True)
class HybridGeometryAuditThresholds:
    min_alignment_pairs: int = 3
    min_alignment_inliers: int = 3
    warn_low_inliers: int = 10
    warn_outlier_ratio: float = 0.50
    fail_outlier_ratio: float = 0.85
    warn_rms_error_sheet: float = 0.35
    fail_rms_error_sheet: float = 0.75
    warn_max_error_sheet: float = 1.0
    fail_max_error_sheet: float = 2.0
    warn_fallback_ratio: float = 0.50
    fail_fallback_ratio: float = 0.80
    warn_coarse_ratio: float = 0.50
    fail_coarse_ratio: float = 0.80

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_alignment_pairs": self.min_alignment_pairs,
            "min_alignment_inliers": self.min_alignment_inliers,
            "warn_low_inliers": self.warn_low_inliers,
            "warn_outlier_ratio": self.warn_outlier_ratio,
            "fail_outlier_ratio": self.fail_outlier_ratio,
            "warn_rms_error_sheet": self.warn_rms_error_sheet,
            "fail_rms_error_sheet": self.fail_rms_error_sheet,
            "warn_max_error_sheet": self.warn_max_error_sheet,
            "fail_max_error_sheet": self.fail_max_error_sheet,
            "warn_fallback_ratio": self.warn_fallback_ratio,
            "fail_fallback_ratio": self.fail_fallback_ratio,
            "warn_coarse_ratio": self.warn_coarse_ratio,
            "fail_coarse_ratio": self.fail_coarse_ratio,
        }


def _worst_status(statuses: list[str]) -> str:
    if not statuses:
        return "ok"
    return max(statuses, key=lambda item: SEVERITY_RANK.get(item, 0))


def _ratio(numerator: int | float, denominator: int | float) -> float:
    denominator = float(denominator or 0)
    if denominator <= 0:
        return 0.0
    return float(numerator or 0) / denominator


def _issue(
    issues: list[dict[str, Any]],
    *,
    severity: str,
    source: str,
    view: str | None,
    code: str,
    message: str,
    metrics: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "severity": severity,
        "source": source,
        "code": code,
        "message": message,
    }
    if view:
        payload["view"] = view
    if metrics:
        payload["metrics"] = metrics
    issues.append(payload)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _audit_alignment_view(
    *,
    source_label: str,
    view_name: str,
    payload: dict[str, Any],
    thresholds: HybridGeometryAuditThresholds,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    status = str(payload.get("status") or "unknown")
    n_pairs = _as_int(payload.get("n_pairs"))
    n_inliers = _as_int(payload.get("n_inliers"))
    n_outliers = _as_int(payload.get("n_outliers"))
    outlier_ratio = _ratio(n_outliers, n_pairs)
    rms_error = _as_float(payload.get("rms_error_sheet"))
    max_error = _as_float(payload.get("max_error_sheet"))

    if status != "ok":
        _issue(
            issues,
            severity="fail",
            source=source_label,
            view=view_name,
            code=f"alignment_{status}",
            message=f"Alignment status is {status}; expected ok",
            metrics={"n_pairs": n_pairs, "n_inliers": n_inliers},
        )
    elif n_pairs < thresholds.min_alignment_pairs:
        _issue(
            issues,
            severity="fail",
            source=source_label,
            view=view_name,
            code="alignment_too_few_pairs",
            message=f"Only {n_pairs} matched pairs; minimum required is {thresholds.min_alignment_pairs}",
            metrics={"n_pairs": n_pairs},
        )
    elif n_inliers < thresholds.min_alignment_inliers:
        _issue(
            issues,
            severity="fail",
            source=source_label,
            view=view_name,
            code="alignment_too_few_inliers",
            message=f"Only {n_inliers} inliers; minimum required is {thresholds.min_alignment_inliers}",
            metrics={"n_pairs": n_pairs, "n_inliers": n_inliers},
        )
    else:
        if n_inliers < thresholds.warn_low_inliers:
            _issue(
                issues,
                severity="warn",
                source=source_label,
                view=view_name,
                code="alignment_low_inliers",
                message=f"Only {n_inliers} inliers; recommended minimum is {thresholds.warn_low_inliers}",
                metrics={"n_pairs": n_pairs, "n_inliers": n_inliers},
            )
        if outlier_ratio >= thresholds.fail_outlier_ratio:
            _issue(
                issues,
                severity="fail",
                source=source_label,
                view=view_name,
                code="alignment_high_outlier_ratio",
                message=f"{n_outliers} of {n_pairs} matched pairs were rejected as outliers",
                metrics={"outlier_ratio": round(outlier_ratio, 6), "n_pairs": n_pairs, "n_outliers": n_outliers},
            )
        elif outlier_ratio >= thresholds.warn_outlier_ratio:
            _issue(
                issues,
                severity="warn",
                source=source_label,
                view=view_name,
                code="alignment_high_outlier_ratio",
                message=f"{n_outliers} of {n_pairs} matched pairs were rejected as outliers",
                metrics={"outlier_ratio": round(outlier_ratio, 6), "n_pairs": n_pairs, "n_outliers": n_outliers},
            )
        if rms_error is not None:
            if rms_error >= thresholds.fail_rms_error_sheet:
                _issue(
                    issues,
                    severity="fail",
                    source=source_label,
                    view=view_name,
                    code="alignment_high_rms_error",
                    message=f"RMS sheet error is {rms_error:.3f}; fail threshold is {thresholds.fail_rms_error_sheet:.3f}",
                    metrics={"rms_error_sheet": rms_error},
                )
            elif rms_error >= thresholds.warn_rms_error_sheet:
                _issue(
                    issues,
                    severity="warn",
                    source=source_label,
                    view=view_name,
                    code="alignment_high_rms_error",
                    message=f"RMS sheet error is {rms_error:.3f}; warn threshold is {thresholds.warn_rms_error_sheet:.3f}",
                    metrics={"rms_error_sheet": rms_error},
                )
        if max_error is not None:
            if max_error >= thresholds.fail_max_error_sheet:
                _issue(
                    issues,
                    severity="fail",
                    source=source_label,
                    view=view_name,
                    code="alignment_high_max_error",
                    message=f"Max sheet error is {max_error:.3f}; fail threshold is {thresholds.fail_max_error_sheet:.3f}",
                    metrics={"max_error_sheet": max_error},
                )
            elif max_error >= thresholds.warn_max_error_sheet:
                _issue(
                    issues,
                    severity="warn",
                    source=source_label,
                    view=view_name,
                    code="alignment_high_max_error",
                    message=f"Max sheet error is {max_error:.3f}; warn threshold is {thresholds.warn_max_error_sheet:.3f}",
                    metrics={"max_error_sheet": max_error},
                )

    view_status = _worst_status([str(issue["severity"]) for issue in issues])
    return (
        {
            "view": view_name,
            "status": view_status,
            "alignment_status": status,
            "n_pairs": n_pairs,
            "n_inliers": n_inliers,
            "n_outliers": n_outliers,
            "outlier_ratio": round(outlier_ratio, 6),
            "rms_error_sheet": rms_error,
            "max_error_sheet": max_error,
        },
        issues,
    )


def _audit_fallback_views(
    *,
    source_label: str,
    hybrid_summary: dict[str, Any],
    alignment_summary: dict[str, Any],
    thresholds: HybridGeometryAuditThresholds,
    total_records: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Detect views with APS fallback geometry that have no alignment data at all.

    Returns (view_audits_for_fallback_only_views, issues).
    """
    issues: list[dict[str, Any]] = []
    view_audits: list[dict[str, Any]] = []
    view_source_counts = hybrid_summary.get("view_source_counts")
    if not isinstance(view_source_counts, dict):
        return view_audits, issues

    for view_name, source_counts_for_view in sorted(view_source_counts.items()):
        if not isinstance(source_counts_for_view, dict):
            continue
        fallback_count = _as_int(source_counts_for_view.get("aps_fragment_fallback"))
        if fallback_count == 0:
            continue
        if view_name in alignment_summary:
            continue

        view_total = sum(_as_int(v) for v in source_counts_for_view.values())
        global_fallback_share = _ratio(fallback_count, total_records)

        if global_fallback_share >= thresholds.fail_fallback_ratio:
            severity = "fail"
        else:
            severity = "warn"

        _issue(
            issues,
            severity=severity,
            source=source_label,
            view=view_name,
            code="fallback_only_view",
            message=(
                f"View '{view_name}' has {fallback_count} of {view_total} records from APS fallback "
                f"with no DXF alignment data ({global_fallback_share * 100:.1f}% of total)"
            ),
            metrics={
                "fallback_count": fallback_count,
                "view_total": view_total,
                "global_fallback_share": round(global_fallback_share, 6),
            },
        )
        view_audits.append(
            {
                "view": view_name,
                "status": severity,
                "alignment_status": "missing",
                "n_pairs": 0,
                "n_inliers": 0,
                "n_outliers": 0,
                "outlier_ratio": 0.0,
                "rms_error_sheet": None,
                "max_error_sheet": None,
                "fallback_only": True,
                "fallback_count": fallback_count,
                "view_total": view_total,
            }
        )

    return view_audits, issues


def _audit_source_mix(
    *,
    source_label: str,
    hybrid_summary: dict[str, Any],
    thresholds: HybridGeometryAuditThresholds,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    record_count = _as_int(hybrid_summary.get("record_count"))
    source_counts = hybrid_summary.get("source_counts") if isinstance(hybrid_summary.get("source_counts"), dict) else {}
    quality_counts = hybrid_summary.get("quality_counts") if isinstance(hybrid_summary.get("quality_counts"), dict) else {}
    fallback_count = _as_int(source_counts.get("aps_fragment_fallback"))
    coarse_count = _as_int(quality_counts.get("coarse"))
    fallback_ratio = _ratio(fallback_count, record_count)
    coarse_ratio = _ratio(coarse_count, record_count)

    if record_count <= 0:
        _issue(
            issues,
            severity="fail",
            source=source_label,
            view=None,
            code="hybrid_no_records",
            message="Hybrid geometry produced no records",
            metrics={"record_count": record_count},
        )
        return issues

    if fallback_ratio >= thresholds.fail_fallback_ratio:
        severity = "fail"
    elif fallback_ratio >= thresholds.warn_fallback_ratio:
        severity = "warn"
    else:
        severity = ""
    if severity:
        _issue(
            issues,
            severity=severity,
            source=source_label,
            view=None,
            code="hybrid_high_fallback_ratio",
            message=f"{fallback_count} of {record_count} records came from APS fallback",
            metrics={"fallback_ratio": round(fallback_ratio, 6), "fallback_count": fallback_count, "record_count": record_count},
        )

    if coarse_ratio >= thresholds.fail_coarse_ratio:
        severity = "fail"
    elif coarse_ratio >= thresholds.warn_coarse_ratio:
        severity = "warn"
    else:
        severity = ""
    if severity:
        _issue(
            issues,
            severity=severity,
            source=source_label,
            view=None,
            code="hybrid_high_coarse_ratio",
            message=f"{coarse_count} of {record_count} records have coarse geometry quality",
            metrics={"coarse_ratio": round(coarse_ratio, 6), "coarse_count": coarse_count, "record_count": record_count},
        )

    return issues


def audit_hybrid_geometry_manifest(
    manifest: dict[str, Any],
    *,
    thresholds: HybridGeometryAuditThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or HybridGeometryAuditThresholds()
    sources: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    total_records = 0
    good_records = 0
    coarse_records = 0
    views_by_status = {"ok": 0, "warn": 0, "fail": 0}

    for result in manifest.get("results") or []:
        if not isinstance(result, dict):
            continue
        source = result.get("source") if isinstance(result.get("source"), dict) else {}
        source_label = str(source.get("label") or source.get("file_name") or result.get("artifact_prefix") or "source")
        alignment_summary = result.get("alignment_summary") if isinstance(result.get("alignment_summary"), dict) else {}
        hybrid_summary = result.get("hybrid_summary") if isinstance(result.get("hybrid_summary"), dict) else {}
        quality_counts = hybrid_summary.get("quality_counts") if isinstance(hybrid_summary.get("quality_counts"), dict) else {}
        record_count = _as_int(hybrid_summary.get("record_count"))
        total_records += record_count
        good_records += _as_int(quality_counts.get("good"))
        coarse_records += _as_int(quality_counts.get("coarse"))

        view_audits: list[dict[str, Any]] = []
        for view_name, view_payload in sorted(alignment_summary.items()):
            if not isinstance(view_payload, dict):
                continue
            view_audit, view_issues = _audit_alignment_view(
                source_label=source_label,
                view_name=str(view_name),
                payload=view_payload,
                thresholds=thresholds,
            )
            view_audits.append(view_audit)
            views_by_status[view_audit["status"]] += 1
            issues.extend(view_issues)

        fallback_view_audits, fallback_view_issues = _audit_fallback_views(
            source_label=source_label,
            hybrid_summary=hybrid_summary,
            alignment_summary=alignment_summary,
            thresholds=thresholds,
            total_records=record_count,
        )
        for fv_audit in fallback_view_audits:
            view_audits.append(fv_audit)
            status_key = fv_audit["status"]
            if status_key in views_by_status:
                views_by_status[status_key] += 1
        issues.extend(fallback_view_issues)

        source_issues = _audit_source_mix(
            source_label=source_label,
            hybrid_summary=hybrid_summary,
            thresholds=thresholds,
        )
        issues.extend(source_issues)
        source_status = _worst_status(
            [str(view["status"]) for view in view_audits]
            + [str(issue["severity"]) for issue in source_issues]
        )
        sources.append(
            {
                "source": source_label,
                "status": source_status,
                "discipline": source.get("discipline"),
                "file_name": source.get("file_name"),
                "record_count": record_count,
                "good_records": _as_int(quality_counts.get("good")),
                "coarse_records": _as_int(quality_counts.get("coarse")),
                "views": view_audits,
            }
        )

    issue_counts = {"warn": 0, "fail": 0}
    for item in issues:
        severity = str(item.get("severity") or "")
        if severity in issue_counts:
            issue_counts[severity] += 1

    status = _worst_status([str(source["status"]) for source in sources])
    return {
        "schema_version": "hybrid_geometry_audit.v1",
        "status": status,
        "thresholds": thresholds.to_dict(),
        "summary": {
            "source_count": len(sources),
            "views_ok": views_by_status["ok"],
            "views_warn": views_by_status["warn"],
            "views_fail": views_by_status["fail"],
            "total_records": total_records,
            "good_records": good_records,
            "coarse_records": coarse_records,
            "issues_warn": issue_counts["warn"],
            "issues_fail": issue_counts["fail"],
        },
        "sources": sources,
        "issues": issues,
    }


def _format_ratio(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _format_number(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_hybrid_geometry_audit_markdown(audit: dict[str, Any]) -> str:
    """Render a concise, human-readable audit summary."""
    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    status = str(audit.get("status") or "unknown").upper()
    lines = [
        "# Hybrid Geometry Audit",
        "",
        f"- Status: `{status}`",
        f"- Sources: `{summary.get('source_count', 0)}`",
        f"- Views: `{summary.get('views_ok', 0)} ok`, `{summary.get('views_warn', 0)} warn`, `{summary.get('views_fail', 0)} fail`",
        f"- Records: `{summary.get('total_records', 0)}` total, `{summary.get('good_records', 0)}` good, `{summary.get('coarse_records', 0)}` coarse",
        f"- Issues: `{summary.get('issues_warn', 0)}` warn, `{summary.get('issues_fail', 0)}` fail",
        "",
        "## Sources",
        "",
        "| Source | Status | Records | Good | Coarse | Views ok/warn/fail |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]

    for source in audit.get("sources") or []:
        if not isinstance(source, dict):
            continue
        views = source.get("views") if isinstance(source.get("views"), list) else []
        view_counts = {"ok": 0, "warn": 0, "fail": 0}
        for view in views:
            if isinstance(view, dict):
                view_status = str(view.get("status") or "ok")
                if view_status in view_counts:
                    view_counts[view_status] += 1
        lines.append(
            "| {source} | `{status}` | {records} | {good} | {coarse} | {ok}/{warn}/{fail} |".format(
                source=str(source.get("source") or ""),
                status=str(source.get("status") or "unknown"),
                records=source.get("record_count", 0),
                good=source.get("good_records", 0),
                coarse=source.get("coarse_records", 0),
                ok=view_counts["ok"],
                warn=view_counts["warn"],
                fail=view_counts["fail"],
            )
        )

    lines.extend(
        [
            "",
            "## View Alignment",
            "",
            "| Source | View | Status | Pairs | Inliers | Outliers | Outlier ratio | RMS | Max |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for source in audit.get("sources") or []:
        if not isinstance(source, dict):
            continue
        source_name = str(source.get("source") or "")
        for view in source.get("views") or []:
            if not isinstance(view, dict):
                continue
            lines.append(
                "| {source} | {view} | `{status}` | {pairs} | {inliers} | {outliers} | {ratio} | {rms} | {max_error} |".format(
                    source=source_name,
                    view=str(view.get("view") or ""),
                    status=str(view.get("status") or "unknown"),
                    pairs=view.get("n_pairs", 0),
                    inliers=view.get("n_inliers", 0),
                    outliers=view.get("n_outliers", 0),
                    ratio=_format_ratio(view.get("outlier_ratio")),
                    rms=_format_number(view.get("rms_error_sheet")),
                    max_error=_format_number(view.get("max_error_sheet")),
                )
            )

    issues = [item for item in (audit.get("issues") or []) if isinstance(item, dict)]
    lines.extend(["", "## Issues", ""])
    if not issues:
        lines.append("No issues detected.")
    else:
        lines.extend(["| Severity | Source | View | Code | Message |", "| --- | --- | --- | --- | --- |"])
        for issue in issues:
            lines.append(
                "| `{severity}` | {source} | {view} | `{code}` | {message} |".format(
                    severity=str(issue.get("severity") or ""),
                    source=str(issue.get("source") or ""),
                    view=str(issue.get("view") or "-"),
                    code=str(issue.get("code") or ""),
                    message=str(issue.get("message") or "").replace("|", "\\|"),
                )
            )

    return "\n".join(lines) + "\n"


def audit_hybrid_geometry_manifest_file(
    manifest_path: Path,
    *,
    output_path: Path | None = None,
    markdown_output_path: Path | None = None,
    thresholds: HybridGeometryAuditThresholds | None = None,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = audit_hybrid_geometry_manifest(manifest, thresholds=thresholds)
    audit["manifest_path"] = str(manifest_path)
    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_output_path is not None:
        Path(markdown_output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(markdown_output_path).write_text(render_hybrid_geometry_audit_markdown(audit), encoding="utf-8")
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit hybrid geometry manifest quality")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args(argv)

    audit = audit_hybrid_geometry_manifest_file(
        args.manifest,
        output_path=args.output,
        markdown_output_path=args.markdown_output,
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit["status"] != "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())
