"""Human/architect-facing clash review PDF."""

from __future__ import annotations

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import Spacer

from app.services.clash_reports.data import ReportBundle, executive_summary
from app.services.clash_reports.formatting import format_optional
from app.services.clash_reports.pdf_base import (
    P,
    P_alias,
    build_pdf,
    data_table,
    field_table,
    meta_block,
    page_break_landscape,
    page_break_portrait,
)

_PAGE_W = A4[0] - 36 * mm


def _instructions_block() -> list:
    return [
        P("Como usar este reporte", "h3"),
        P(
            "Este documento es su bitacora de validacion manual. Abra los DWG indicados, "
            "ejecute el comando de zoom sugerido, active las capas relevantes y marque la decision "
            "en la bitacora final.",
            "body",
        ),
        Spacer(1, 6),
        P("Instrucciones generales", "h3"),
        P("Paso 1 - Abrir los dos archivos en AutoCAD", "body"),
        P("1. Abra AutoCAD.", "body"),
        P("2. Abra el Plano A (primera disciplina del par).", "body"),
        P("3. Abra el Plano B en la misma sesion.", "body"),
        P("4. Use Ventanas en mosaico o DWG Compare para superponer.", "body"),
        Spacer(1, 4),
        P("Paso 2 - Ir a las coordenadas", "body"),
        P("Copie el comando Z W de cada tarjeta y peguelo en la linea de comandos.", "body"),
        P("Todos los valores estan en milimetros.", "small"),
        Spacer(1, 4),
        P("Paso 3 - Controlar capas", "body"),
        P("Apague capas irrelevantes y encienda solo las dos capas del clash.", "body"),
        Spacer(1, 4),
        P("Paso 4 - Decision final", "body"),
        data_table(
            ["Decision", "Significado"],
            [
                ["CLASH REAL", "Conflicto real de coordinacion."],
                ["FALSO POSITIVO", "Ruido grafico (marcos, cotas, anotaciones)."],
                ["PENDIENTE", "Requiere mas informacion."],
            ],
            col_widths=[35 * mm, _PAGE_W - 35 * mm],
        ),
        Spacer(1, 8),
    ]


def _summary_cards(summary: dict[str, str]) -> list:
    return [
        field_table(
            [
                ("Incidencias primarias", summary["incidents"]),
                ("Conflictos agrupados", summary["conflicts"]),
                ("Niveles afectados", summary["levels"]),
                ("Grupo prioritario", summary["top_group"]),
                ("Area total solapada", summary["total_area"]),
            ],
            label_width=55 * mm,
        ),
        Spacer(1, 8),
    ]


def _review_order_table(bundle: ReportBundle) -> list:
    if not bundle.groups:
        return [P("No hay grupos de revision (sin incidencias).", "body"), Spacer(1, 6)]
    rows = [
        [
            g.code,
            g.discipline_pair,
            f"{g.layer_a} / {g.layer_b}",
            str(g.incident_count),
            f"{g.total_area_m2:.2f} m2",
            g.priority,
        ]
        for g in bundle.groups
    ]
    return [
        data_table(
            ["Grupo", "Disciplinas", "Capas", "Inc.", "Area total", "Prioridad"],
            rows,
            col_widths=[18 * mm, 32 * mm, 38 * mm, 12 * mm, 24 * mm, 28 * mm],
        ),
        Spacer(1, 8),
    ]


def _incident_card(inc) -> list:
    zoom_line = inc.zoom_command or inc.zoom_fallback or "no disponible"
    zoom_style = "mono" if inc.zoom_command else "body"
    return [
        P(f"{inc.human_code} - {inc.incident_id}", "h3"),
        field_table(
            [
                ("Codigo humano", inc.human_code),
                ("ID programa", inc.incident_id),
                ("Severidad", inc.severity),
                ("Confianza", inc.confidence),
                ("Nivel", inc.level_id),
                ("Disciplinas", f"{inc.discipline_a} / {inc.discipline_b}"),
                ("Archivos (alias)", f"{inc.file_a_alias} x {inc.file_b_alias}"),
                ("Capa A / Capa B", f"{format_optional(inc.layer_a)} / {format_optional(inc.layer_b)}"),
                ("Area", inc.area_m2_text),
                ("Profundidad Z", inc.z_depth_text),
                ("Centro", inc.center_text),
                ("Limites", inc.bounds_text),
                ("Elementos", str(inc.member_count)),
            ],
            label_width=42 * mm,
        ),
        Spacer(1, 4),
        P("Comando AutoCAD:", "body"),
        P(zoom_line, zoom_style),
        Spacer(1, 4),
        P("Que verificar:", "body"),
        P(inc.what_to_check, "body"),
        Spacer(1, 4),
        P("Decision: [ ] CLASH REAL   [ ] FALSO POSITIVO   [ ] PENDIENTE", "body"),
        P("Notas del revisor: _________________________________________________", "body"),
        Spacer(1, 10),
    ]


def _validation_log(bundle: ReportBundle) -> list:
    if not bundle.incidents:
        return [P("Sin filas de validacion (no hay incidencias).", "body")]
    rows = [
        [
            inc.human_code,
            inc.incident_id,
            inc.level_id,
            P_alias(f"{inc.file_a_alias}/{inc.file_b_alias}"),
            f"{format_optional(inc.layer_a)}/{format_optional(inc.layer_b)}",
            inc.area_m2_text,
            "[ ] R  [ ] F  [ ] P",
            "",
            "",
        ]
        for inc in bundle.incidents
    ]
    landscape_w = landscape(A4)[0] - 36 * mm
    return [
        *page_break_landscape(),
        P("Bitacora de validacion", "h2"),
        Spacer(1, 4),
        data_table(
            ["Codigo", "ID", "Nivel", "Archivos", "Capas", "Area", "Decision", "Notas", "Fecha"],
            rows,
            col_widths=[16 * mm, 22 * mm, 16 * mm, 34 * mm, 28 * mm, 18 * mm, 22 * mm, landscape_w - 178 * mm, 22 * mm],
        ),
        Spacer(1, 8),
        *page_break_portrait(),
    ]


def _filename_legend(bundle: ReportBundle) -> list:
    legend = bundle.alias_registry.legend
    if not legend:
        return []
    rows = [
        [P_alias(e["alias"]), e["full_name"], e["discipline"], e["level"]]
        for e in legend
    ]
    return [
        P("Leyenda de alias de archivos", "h2"),
        Spacer(1, 4),
        data_table(
            ["Alias", "Nombre completo", "Disciplina", "Nivel"],
            rows,
            col_widths=[28 * mm, 72 * mm, 28 * mm, 22 * mm],
        ),
    ]


def build_human_pdf(bundle: ReportBundle) -> bytes:
    meta = bundle.meta
    summary = executive_summary(bundle)
    status = "validacion manual requerida" if bundle.incidents else "sin incidencias primarias"

    story: list = [
        P("Guia de Revision Manual de Clashes", "title"),
        meta_block(
            [
                ("Proyecto", str(meta.get("project_name", ""))),
                ("Carpeta", str(meta.get("folder_name", ""))),
                ("Corrida N.", f"{int(meta.get('run_sequence') or 1):02d}"),
                ("Fecha", str(meta.get("run_date", ""))),
                ("Exportado por", str(meta.get("user_display", ""))),
                ("Revisor previsto", "Arquitecto / coordinador de obra"),
                ("Estado", status),
            ]
        ),
        Spacer(1, 10),
        P("Resumen ejecutivo", "h2"),
        *_summary_cards(summary),
        *_instructions_block(),
        P("Orden de revision recomendado", "h2"),
        *_review_order_table(bundle),
    ]

    if bundle.incidents:
        story.append(P("Tarjetas de incidencia", "h2"))
        story.append(Spacer(1, 4))
        for inc in bundle.incidents:
            story.extend(_incident_card(inc))
    else:
        story.append(P("Estado - Sin incidencias primarias", "h2"))
        story.append(
            P(
                "El analisis completo los pares programados y no encontro conflictos "
                "geometricos entre elementos primarios en las capas detectadas.",
                "body",
            )
        )

    story.extend(_validation_log(bundle))
    story.extend(_filename_legend(bundle))

    meta_line = (
        f"{meta.get('project_name', '')} | {meta.get('folder_name', '')} | "
        f"Corrida {int(meta.get('run_sequence') or 1):02d}"
    )
    return build_pdf(story, title="Guia de Revision Manual de Clashes", meta_line=meta_line)
