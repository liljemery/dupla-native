"""
BC3 chapter configuration for the electrical discipline.
"""

from __future__ import annotations

from disciplines.base import ChapterConfig, ChapterDefinition

CHAPTERS: dict[str, ChapterDefinition] = {
    "01": ChapterDefinition(
        code="01",
        title="CANALIZACIONES Y TUBERIAS",
        desc="Tuberias EMT, PVC, conduit, canaletas, bandejas portacables",
        tokens={
            "tubo", "tuberia", "emt", "conduit", "canaleta",
            "bandeja", "ducto", "pvc elec", "canalizac",
        },
    ),
    "02": ChapterDefinition(
        code="02",
        title="CABLEADO Y CONDUCTORES",
        desc="Cables THW, THHN, romex, fibra optica, cable coaxial, cable de datos",
        tokens={
            "cable", "conductor", "thw", "thhn", "romex",
            "fibra", "coaxial", "awg", "alambre",
        },
    ),
    "03": ChapterDefinition(
        code="03",
        title="PANELES Y PROTECCIONES",
        desc="Paneles de breakers, interruptores principales, barras de tierra, supresores",
        tokens={
            "panel", "breaker", "interruptor principal", "barra tierra",
            "supresor", "transferencia", "tablero", "proteccion",
        },
    ),
    "04": ChapterDefinition(
        code="04",
        title="SALIDAS E INTERRUPTORES",
        desc="Tomacorrientes 110V/220V, interruptores sencillos/dobles/triples, dimmers",
        tokens={
            "tomacorr", "interrup", "switch", "dimmer",
            "outlet", "110v", "220v", "salida", "toma",
        },
    ),
    "05": ChapterDefinition(
        code="05",
        title="LUMINARIAS Y ALUMBRADO",
        desc="Luminarias de techo, pared, empotradas, emergencia, exteriores",
        tokens={
            "lumin", "alumbr", "lampara", "led", "fluoresc",
            "spot", "downlight", "emergencia", "aplique",
        },
    ),
    "06": ChapterDefinition(
        code="06",
        title="SISTEMAS ESPECIALES",
        desc="Intercomunicadores, CCTV, deteccion de incendios, sonido, control de acceso",
        tokens={
            "intercom", "cctv", "incendio", "detec", "humo",
            "alarma", "sonido", "control acceso", "data",
        },
    ),
    "07": ChapterDefinition(
        code="07",
        title="ACOMETIDA Y MEDICION",
        desc="Acometida electrica, medidores, transformadores, postes",
        tokens={
            "acometida", "medidor", "transform", "poste",
            "tierra", "pararrayos", "sub-estacion",
        },
    ),
    "09": ChapterDefinition(
        code="09",
        title="GASTOS GENERALES ELECTRICO",
        desc="Pruebas, certificaciones, permisos, mano de obra especializada",
        tokens={
            "prueba", "certificac", "permiso", "gastos",
            "supervisi", "indirect",
        },
    ),
}

ITEM_TYPE_TO_CHAPTER: dict[str, str] = {
    "fixture_count": "04",
}

PREFIX_TO_CHAPTER: list[tuple[str, str]] = [
    ("fixture_", "04"),
]

STATIC_GUIDANCE: dict[str, str] = {
    "01": "Canalizaciones: tuber\u00edas y ductos. Unidad ML o tramo.",
    "02": "Cableado: conductores por metro o rollo. Especificar calibre AWG.",
    "03": "Paneles: tableros por unidad. Incluir capacidad en amperios.",
    "04": "Salidas: tomacorrientes e interruptores por punto o unidad.",
    "05": "Luminarias: por unidad. Diferenciar tipo y potencia.",
    "06": "Sistemas especiales: por punto o unidad. Incluir tipo.",
    "07": "Acometida: por global o unidad seg\u00fan componente.",
    "09": "Gastos generales el\u00e9ctricos.",
}


def build_chapter_config() -> ChapterConfig:
    return ChapterConfig(
        chapters=CHAPTERS,
        item_type_to_chapter=ITEM_TYPE_TO_CHAPTER,
        prefix_to_chapter=PREFIX_TO_CHAPTER,
        static_guidance=STATIC_GUIDANCE,
        default_chapter="09",
    )
