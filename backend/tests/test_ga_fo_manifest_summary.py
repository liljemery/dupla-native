from app.config import Settings
from app.services.aps_derivative_pipeline import (
    _manifest_covers_views,
    _manifest_failure_summary,
    _translation_views_list,
    build_manifest_summary,
)


def test_build_manifest_summary_truncates():
    manifest = {
        "version": "1.0",
        "progress": "complete",
        "derivatives": [
            {
                "name": "root",
                "children": [
                    {"name": "Sheet A", "role": "2d", "type": "geometry"},
                    {"name": "View3D", "role": "3d", "type": "geometry"},
                ],
            }
        ],
    }
    s = build_manifest_summary(manifest, 500)
    assert "Sheet A" in s
    assert len(s) <= 500


def test_build_manifest_summary_empty_derivatives():
    s = build_manifest_summary({"derivatives": []}, 2000)
    assert "nodes_sample" in s


def test_translation_views_list_parses_csv():
    s = Settings.model_construct(aps_translation_views="3d, 2d")
    assert _translation_views_list(s) == ["3d", "2d"]


def test_manifest_covers_views_2d_from_children():
    manifest = {
        "status": "success",
        "derivatives": [{"name": "root", "children": [{"name": "A", "role": "2d", "type": "geometry"}]}],
    }
    s = Settings.model_construct(aps_translation_views="2d")
    assert _manifest_covers_views(manifest, _translation_views_list(s)) is True


def test_manifest_failure_summary_includes_reason_and_messages():
    data = {
        "progress": "complete",
        "reason": "Unsupported extension",
        "derivatives": [{"name": "root", "progress": "failed", "messages": [{"type": "error", "code": "X"}]}],
    }
    s = _manifest_failure_summary(data, max_len=5000)
    assert "Unsupported extension" in s
    assert "messages" in s
