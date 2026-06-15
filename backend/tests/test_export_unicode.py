"""PDF exports must tolerate Unicode project names and file labels."""

from app.services.export_service import ExportService


def test_documentary_report_pdf_supports_unicode_project_name() -> None:
    svc = ExportService(session=None, workspace_id=None)  # type: ignore[arg-type]
    data = svc.build_documentary_report_pdf(
        project_name="SERENA 18 — Test Clashes 4 planos",
        project_code=None,
        location_text="Ciudad de México",
        client_name="Cliente — demo",
        criteria=[{"label": "Ítem requerido", "required": True, "done": False}],
        files=[],
    )
    assert data[:4] == b"%PDF"
