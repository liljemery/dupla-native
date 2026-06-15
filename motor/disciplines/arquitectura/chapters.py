"""
BC3 chapter configuration for the architectural discipline.

Extracted from agents/classifier_agent.py -- these definitions drive
how takeoffs are grouped for OpenAI classification and which BC3 items
are filtered per chapter.
"""

from __future__ import annotations

from disciplines.base import ChapterConfig, ChapterDefinition

CHAPTERS: dict[str, ChapterDefinition] = {
    "01": ChapterDefinition(
        code="01",
        title="MOVIMIENTO DE TIERRAS",
        desc="Excavacion, relleno, compactacion, zapatas, cimentacion, bote de material",
        tokens={"excavac", "rellen", "compac", "zapata", "ciment", "bote", "movim", "tierr", "suelo"},
    ),
    "02": ChapterDefinition(
        code="02",
        title="HORMIGON ARMADO / ESTRUCTURA",
        desc="Hormigon armado, acero de refuerzo, columnas, vigas, losas, escaleras, encofrado",
        tokens={
            "hormig", "armad", "colum", "viga", "losa", "escal", "encof",
            "acero", "refuerz", "concret", "estruc", "zapata", "fundac",
            "varilla", "fierro",
        },
    ),
    "03": ChapterDefinition(
        code="03",
        title="MUROS Y PANETE",
        desc="Muros de bloques, panete interior y exterior, revestimientos",
        tokens={
            "muro", "bloque", "panete", "panet", "revest",
            "mampost", "tabiq", "pared", "bloc", "mortero",
        },
    ),
    "04": ChapterDefinition(
        code="04",
        title="PISOS Y CERAMICA",
        desc="Pisos ceramica, porcelanato, zocalos, pulido, nivelacion",
        tokens={
            "piso", "ceramic", "porcelan", "zocal", "pulid", "nivel",
            "terrazo", "porcela", "baldos", "contrap",
        },
    ),
    "05": ChapterDefinition(
        code="05",
        title="PUERTAS Y VENTANAS",
        desc="Puertas metalicas PVC madera, ventanas aluminio vidrio, herrajes",
        tokens={
            "puerta", "ventana", "herraje", "vidrio", "alumin",
            "cerradura", "bisagra", "marco", "hoja", "persiana",
        },
    ),
    "06": ChapterDefinition(
        code="06",
        title="INSTALACIONES ELECTRICAS",
        desc="Puntos electricos, cableado, interruptores, tomas, paneles, luminarias",
        tokens={
            "electr", "cable", "interrup", "toma", "panel", "lumin",
            "tubo", "conduit", "breaker", "tomacorr", "switch",
        },
    ),
    "07": ChapterDefinition(
        code="07",
        title="SANITARIAS Y PLOMERIA",
        desc="Inodoros, lavamanos, duchas, tuberias PVC, cisterna, bombas, drenaje",
        tokens={
            "sanitar", "inodor", "lavam", "ducha", "tuberia", "cistern",
            "bomb", "drenaj", "plomer", "acueduc", "bano", "wc",
        },
    ),
    "08": ChapterDefinition(
        code="08",
        title="PINTURA Y ACABADOS",
        desc="Pintura interior y exterior, impermeabilizante, sellador",
        tokens={
            "pintura", "imperm", "sellad", "acabad", "lacado",
            "esmalt", "latex", "paint",
        },
    ),
    "09": ChapterDefinition(
        code="09",
        title="GASTOS GENERALES",
        desc="Supervision, topografia, seguridad, limpieza, andamios, gastos indirectos",
        tokens={
            "supervis", "topogr", "segur", "limpiez", "andami",
            "gastos", "indirect", "administr", "imprevist",
        },
    ),
}

ITEM_TYPE_TO_CHAPTER: dict[str, str] = {
    "beam_concrete_volume": "02",
    "beam_volume": "02",
    "beam_area": "02",
    "beam_length": "02",
    "beam_count": "02",
    "beam_formwork_area_hint": "02",
    "beam_reinforcement_kg": "02",
    "column_concrete_volume": "02",
    "column_volume": "02",
    "column_area": "02",
    "column_length": "02",
    "column_count": "02",
    "column_formwork_area_hint": "02",
    "column_reinforcement_kg": "02",
    "slab_concrete_volume": "02",
    "slab_area": "02",
    "slab_count": "02",
    "slab_formwork_area_hint": "02",
    "slab_reinforcement_kg": "02",
    "footing_concrete_volume": "02",
    "footing_volume": "02",
    "footing_area": "02",
    "footing_formwork_area_hint": "02",
    "footing_reinforcement_kg": "02",
    "structural_count": "02",
    "structural_area": "02",
    "structural_volume": "02",
    "structural_length": "02",
    "stair_count": "02",
    "wall_net_area": "03",
    "wall_volume": "03",
    "wall_waterproofing": "03",
    "wall_finish_plaster": "03",
    "wall_gross_area": "03",
    "floor_area": "04",
    "floor_finish": "04",
    "floor_waterproofing": "07",
    "door_leaf_wood_count": "05",
    "door_frame_count": "05",
    "door_hardware_set_count": "05",
    "door_count": "05",
    "window_frame_count": "05",
    "window_glazing_area": "05",
    "window_count": "05",
    "wall_finish_paint": "08",
    "ceiling_area": "08",
    "ceiling_finish_paint": "08",
    "wet_area_fixture_count": "07",
    "wet_area_area": "07",
    "fixture_count": "06",
}

PREFIX_TO_CHAPTER: list[tuple[str, str]] = [
    ("beam_", "02"),
    ("column_", "02"),
    ("slab_", "02"),
    ("footing_", "02"),
    ("structural_", "02"),
    ("stair_", "02"),
    ("wall_finish_paint", "08"),
    ("wall_finish_plast", "03"),
    ("wall_net", "03"),
    ("wall_vol", "03"),
    ("wall_water", "03"),
    ("wall_", "03"),
    ("floor_area", "04"),
    ("floor_finish", "04"),
    ("floor_water", "07"),
    ("floor_", "04"),
    ("ceiling_", "08"),
    ("door_", "05"),
    ("window_", "05"),
    ("wet_area_", "07"),
    ("fixture_", "06"),
]

STATIC_GUIDANCE: dict[str, str] = {
    "01": (
        "Cap. tierras: excavaci\u00f3n, relleno, compactaci\u00f3n, transporte de material; "
        "no mezclar con hormig\u00f3n armado (cap.02). Unidad suele ser m3 o m2 seg\u00fan partida."
    ),
    "02": (
        "Cap. estructura: hormig\u00f3n armado, encofrados, acero por kg, vigas/columnas/losas/zapatas; "
        "respeta m3 vs m2 vs kg del takeoff."
    ),
    "03": (
        "Cap. muros: bloques, mampostería, tabiques, mortero; m2 de muro o m3 seg\u00fan partida; "
        "pa\u00f1ete/revoque fino suele ir en acabados (cap.08) si el takeoff es pintura/revoque."
    ),
    "04": (
        "Cap. pisos y cer\u00e1mica: porcelanato, cer\u00e1mica, contrapiso, nivelaci\u00f3n; "
        "unidad m2 salvo partidas por ud."
    ),
    "05": (
        "Cap. carpinter\u00edas: puertas y ventanas, marcos, vidrios, herrajes; "
        "ud para hojas/marcos, m2 para vidrio o paneles seg\u00fan cat\u00e1logo."
    ),
    "06": (
        "Cap. el\u00e9ctrico: puntos, cableado, tableros, luminarias; "
        "no asignar partidas sanitarias a takeoffs el\u00e9ctricos."
    ),
    "07": (
        "Cap. sanitario/plomer\u00eda: inodoros, lavamanos, tuber\u00edas PVC, drenaje; "
        "no confundir con el\u00e9ctrico."
    ),
    "08": (
        "Cap. pintura y acabados: pintura, selladores, impermeabilizantes de acabado; "
        "m2 habitual en muros/cielos."
    ),
    "09": (
        "Cap. gastos generales: supervisi\u00f3n, limpieza, seguridad, indirectos; "
        "solo si el takeoff es claramente administrativo/indirecto."
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
