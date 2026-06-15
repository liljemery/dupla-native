"""
BC3 chapter configuration for the sanitary/plumbing discipline.
"""

from __future__ import annotations

from disciplines.base import ChapterConfig, ChapterDefinition

CHAPTERS: dict[str, ChapterDefinition] = {
    "01": ChapterDefinition(
        code="01",
        title="AGUA POTABLE",
        desc="Tuberias de agua fria y caliente, valvulas, llaves de paso, medidores",
        tokens={
            "agua", "potable", "cpvc", "pvc", "tuberia",
            "valvula", "llave", "medidor", "fria", "caliente",
        },
    ),
    "02": ChapterDefinition(
        code="02",
        title="DRENAJE Y AGUAS RESIDUALES",
        desc="Tuberias de drenaje, registros, trampas, ventilaciones, conexiones sanitarias",
        tokens={
            "drenaje", "residual", "registro", "trampa",
            "ventilac", "sifon", "desague", "cloaca",
        },
    ),
    "03": ChapterDefinition(
        code="03",
        title="APARATOS SANITARIOS",
        desc="Inodoros, lavamanos, duchas, bañeras, bidets, fregaderos, urinarios",
        tokens={
            "inodor", "lavamano", "ducha", "baner", "bidet",
            "fregadero", "urinar", "sanitario", "grifo", "mezclador",
        },
    ),
    "04": ChapterDefinition(
        code="04",
        title="AGUAS PLUVIALES",
        desc="Bajantes pluviales, canaletas, drenaje de techo, cisterna pluvial",
        tokens={
            "pluvial", "bajante", "canal", "lluvia",
            "techo drenaje", "gutter",
        },
    ),
    "05": ChapterDefinition(
        code="05",
        title="SISTEMA DE BOMBEO Y ALMACENAMIENTO",
        desc="Cisternas, bombas, tanques elevados, hidroneumaticos, calentadores",
        tokens={
            "cisterna", "bomba", "tanque", "hidroneum",
            "calentad", "presion", "booster",
        },
    ),
    "06": ChapterDefinition(
        code="06",
        title="GAS",
        desc="Tuberias de gas, valvulas, reguladores, conexiones de gas",
        tokens={
            "gas", "glp", "propano", "regulador",
        },
    ),
    "09": ChapterDefinition(
        code="09",
        title="GASTOS GENERALES SANITARIO",
        desc="Pruebas hidrostaticas, certificaciones, permisos",
        tokens={
            "prueba", "hidrostat", "certificac", "permiso",
            "gastos", "supervisi",
        },
    ),
}

ITEM_TYPE_TO_CHAPTER: dict[str, str] = {
    "wet_area_fixture_count": "03",
    "wet_area_area": "03",
    "wet_area_count": "03",
    "floor_waterproofing": "02",
}

PREFIX_TO_CHAPTER: list[tuple[str, str]] = [
    ("wet_area_", "03"),
]

STATIC_GUIDANCE: dict[str, str] = {
    "01": "Agua potable: tuber\u00edas y accesorios. ML para tuber\u00edas, UD para v\u00e1lvulas.",
    "02": "Drenaje: tuber\u00edas PVC-SDR, registros, trampas. ML para tuber\u00edas, UD para accesorios.",
    "03": "Aparatos sanitarios: por unidad. Incluir calidad (est\u00e1ndar/premium).",
    "04": "Pluviales: bajantes y canaletas. ML para tuber\u00edas.",
    "05": "Bombeo: cisternas, bombas, tanques. Por unidad o global.",
    "06": "Gas: tuber\u00edas y accesorios. ML para tuber\u00edas, UD para reguladores.",
    "09": "Gastos generales sanitarios.",
}


def build_chapter_config() -> ChapterConfig:
    return ChapterConfig(
        chapters=CHAPTERS,
        item_type_to_chapter=ITEM_TYPE_TO_CHAPTER,
        prefix_to_chapter=PREFIX_TO_CHAPTER,
        static_guidance=STATIC_GUIDANCE,
        default_chapter="09",
    )
