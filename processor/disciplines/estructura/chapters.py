"""
BC3 chapter configuration for the structural discipline.

Focused on concrete, reinforcement, formwork, excavation/foundations,
and structural steel.
"""

from __future__ import annotations

from disciplines.base import ChapterConfig, ChapterDefinition

CHAPTERS: dict[str, ChapterDefinition] = {
    "01": ChapterDefinition(
        code="01",
        title="MOVIMIENTO DE TIERRAS",
        desc="Excavacion para zapatas, vigas de amarre, cisternas, relleno y compactacion, bote de material",
        tokens={
            "excavac", "rellen", "compac", "zapata", "ciment", "bote",
            "movim", "tierr", "suelo", "sub-base", "nivelac",
        },
    ),
    "02": ChapterDefinition(
        code="02",
        title="HORMIGON ARMADO",
        desc="Hormigon en zapatas, columnas, vigas, losas, muros de corte, escaleras, cisternas",
        tokens={
            "hormig", "armad", "concret", "vaciado", "ligado",
            "bombeo", "curado", "resistencia", "fc",
        },
    ),
    "03": ChapterDefinition(
        code="03",
        title="ENCOFRADO Y DESENCOFRADO",
        desc="Encofrado metalico y madera para columnas, vigas, losas, zapatas, muros",
        tokens={
            "encof", "desencof", "formaleta", "molde", "madera",
            "metalic", "plywood", "panel",
        },
    ),
    "04": ChapterDefinition(
        code="04",
        title="ACERO DE REFUERZO",
        desc="Varillas, mallas electrosoldadas, alambre de amarre, estribos, bastones, ganchos",
        tokens={
            "acero", "refuerz", "varilla", "malla", "alambre",
            "estribo", "fierro", "kg", "quintal",
        },
    ),
    "05": ChapterDefinition(
        code="05",
        title="CIMENTACIONES",
        desc="Zapatas aisladas, zapatas corridas, vigas de amarre, pedestales, pilotes",
        tokens={
            "zapata", "ciment", "fundac", "pedestal", "pilote",
            "viga amarre", "platea", "radier",
        },
    ),
    "06": ChapterDefinition(
        code="06",
        title="MUROS ESTRUCTURALES",
        desc="Muros de corte, muros de contencion, muros de hormigon armado",
        tokens={
            "muro corte", "muro conten", "muro hormig", "shear",
            "retaining", "cortante",
        },
    ),
    "07": ChapterDefinition(
        code="07",
        title="ESTRUCTURA METALICA",
        desc="Perfiles metalicos, conexiones soldadas y atornilladas, placas base",
        tokens={
            "metal", "perfil", "acero estructural", "soldad",
            "atornill", "placa base", "steel",
        },
    ),
    "09": ChapterDefinition(
        code="09",
        title="GASTOS GENERALES ESTRUCTURA",
        desc="Supervision estructural, pruebas de hormigon, ensayos, certificaciones",
        tokens={
            "supervis", "ensayo", "prueba", "certificac",
            "laboratorio", "gastos", "indirect",
        },
    ),
}

ITEM_TYPE_TO_CHAPTER: dict[str, str] = {
    "beam_concrete_volume": "02",
    "beam_volume": "02",
    "beam_area": "02",
    "beam_length": "02",
    "beam_count": "02",
    "beam_formwork_area_hint": "03",
    "beam_reinforcement_kg": "04",
    "column_concrete_volume": "02",
    "column_volume": "02",
    "column_area": "02",
    "column_length": "02",
    "column_count": "02",
    "column_formwork_area_hint": "03",
    "column_reinforcement_kg": "04",
    "slab_concrete_volume": "02",
    "slab_area": "02",
    "slab_count": "02",
    "slab_formwork_area_hint": "03",
    "slab_reinforcement_kg": "04",
    "footing_concrete_volume": "05",
    "footing_volume": "05",
    "footing_area": "05",
    "footing_formwork_area_hint": "03",
    "footing_reinforcement_kg": "04",
    "structural_count": "02",
    "structural_area": "02",
    "structural_volume": "02",
    "structural_length": "02",
    "stair_count": "02",
}

PREFIX_TO_CHAPTER: list[tuple[str, str]] = [
    ("beam_reinforcement", "04"),
    ("beam_formwork", "03"),
    ("beam_", "02"),
    ("column_reinforcement", "04"),
    ("column_formwork", "03"),
    ("column_", "02"),
    ("slab_reinforcement", "04"),
    ("slab_formwork", "03"),
    ("slab_", "02"),
    ("footing_reinforcement", "04"),
    ("footing_formwork", "03"),
    ("footing_", "05"),
    ("structural_", "02"),
    ("stair_", "02"),
]

STATIC_GUIDANCE: dict[str, str] = {
    "01": (
        "Cap. tierras: solo movimiento de tierras para cimentaciones. "
        "No incluir hormig\u00f3n ni acero aqu\u00ed."
    ),
    "02": (
        "Cap. hormig\u00f3n armado: vaciado de hormig\u00f3n en elementos estructurales. "
        "Unidad principal m3. No incluir encofrado ni acero."
    ),
    "03": (
        "Cap. encofrado: \u00e1reas de contacto para encofrado. "
        "Unidad principal m2. Diferenciar met\u00e1lico vs madera."
    ),
    "04": (
        "Cap. acero de refuerzo: peso de acero en kg o qq. "
        "Incluir mallas electrosoldadas. Diferenciar grado 40 vs 60."
    ),
    "05": (
        "Cap. cimentaciones: zapatas, vigas de amarre, pedestales. "
        "Hormig\u00f3n en cimentaciones va aqu\u00ed, no en cap.02."
    ),
    "06": (
        "Cap. muros estructurales: muros de corte y contenci\u00f3n en hormig\u00f3n. "
        "No confundir con muros de bloques (disciplina arquitect\u00f3nica)."
    ),
    "07": (
        "Cap. estructura met\u00e1lica: solo si hay perfiles/conexiones de acero estructural."
    ),
    "09": (
        "Cap. gastos: supervisi\u00f3n, ensayos de probetas, certificaciones."
    ),
}


def build_chapter_config() -> ChapterConfig:
    return ChapterConfig(
        chapters=CHAPTERS,
        item_type_to_chapter=ITEM_TYPE_TO_CHAPTER,
        prefix_to_chapter=PREFIX_TO_CHAPTER,
        static_guidance=STATIC_GUIDANCE,
        default_chapter="09",
    )
