"""
Deterministic chapter mapping and summary generation for budget composition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core.schemas import BudgetCandidate, QuantityTakeoff

from budget.provenance import append_provenance

STRONG_BC3_SCORE = 0.45
STRONG_BC3_MARGIN = 0.05


@dataclass(frozen=True)
class ChapterSegment:
    code: str
    title: str


def _coerce_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item]
    return [str(value)]


def _takeoff_tags(takeoff: QuantityTakeoff) -> set[str]:
    tags = {
        tag.lower()
        for tag in [
            *_coerce_tags(takeoff.inputs.get("context_tags")),
            *_coerce_tags(takeoff.trace.metadata.get("context_tags")),
        ]
        if tag
    }
    return tags


def _material_hint(takeoff: QuantityTakeoff) -> str | None:
    value = takeoff.inputs.get("material_hint")
    if value is None:
        value = takeoff.trace.metadata.get("material_hint")
    return str(value).lower() if value else None


def select_strong_candidate(
    takeoff: QuantityTakeoff,
    candidates: Iterable[BudgetCandidate],
    *,
    min_score: float = STRONG_BC3_SCORE,
    min_margin: float = STRONG_BC3_MARGIN,
) -> BudgetCandidate | None:
    ranked = sorted(
        (candidate for candidate in candidates if candidate.takeoff_key == takeoff.item_key),
        key=lambda candidate: candidate.score,
        reverse=True,
    )
    if not ranked:
        return None

    top = ranked[0]
    second_score = ranked[1].score if len(ranked) > 1 else 0.0
    
    def _normalize_unit(u: str) -> str:
        return u.lower().strip().replace(" ", "").replace("²", "2").replace("³", "3")

    unit_matches = _normalize_unit(top.unit) == _normalize_unit(takeoff.unit)
    if (unit_matches or top.score > 0.8) and top.score >= min_score and (top.score - second_score) >= min_margin:
        return top
    return None


_DEFAULT_BC3_MAP: dict[str, str] = {
    "wall_net_area": "P0501101",
    "wall_finish_tile": "P08R1012",
    "wall_waterproofing": "P1103101",
    "floor_waterproofing": "P1103101",
    "ceiling_area": "P0501107",
    "ceiling_finish_plaster": "P0501107",
    "ceiling_finish_paint": "P1801111",
    "window_count": "P1601045",
    "window_area": "P1601045",
    "window_installation_count": "P1601045",
    "window_sealant_area": "P1601045",
    "wet_area_waterproofing": "P1103101",
    "wet_area_fixture_count": "P130CON",
    "stair_count": "P1201101",
    "fixture_count": "P130CON",
}

# --- Wall masonry by thickness (from catalog GIV00001) ---
_WALL_10CM = "P0415006"     # Muro bloques 10x20x40 SNP          $945.60
_WALL_15CM_SNP = "P0415005" # Muro bloques 15x20x40 SNP 3/8@40   $1,266.35
_WALL_15CM_BNP = "P0415010" # Muro bloques 15x20x40 BNP 3/8@20   $1,643.48
_WALL_20CM_BNP = "P0420004" # Muro bloques 20x20x40 BNP 3/8@20   $1,979.74
_WALL_20CM_SNP = "P0420009" # Muro bloques 20x20x40 SNP           $2,015.86
_WALL_CONCRETE = "P0303251" # Muro H.A. e=0.15m                   $41,943.84

# --- Plaster/stucco ---
_PLASTER_INT = "P0501101"   # Panete liso muros interiores        $327.63
_PLASTER_EXT = "P0501102"   # Panete liso muros exteriores        $602.90
_PLASTER_COL = "P0501105"   # Panete liso columnas                $447.63
_PLASTER_BEAM = "P0501106"  # Panete liso vigas                   $512.63
_PLASTER_CEIL = "P0501107"  # Panete liso losa techo              $512.63

# --- Paint ---
_PAINT_INT = "P1801101"     # Pintura acrilica interior           $159.60
_PAINT_EXT = "P1801102"     # Pintura acrilica exterior           $303.60
_PAINT_CEIL = "P1801111"    # Pintura economica losas/vigas       $247.80

# --- Doors ---
_DOOR_ANDIROBA_STD = "P1501011"   # Andiroba 0.90x2.10            $16,501.12
_DOOR_ANDIROBA_DBL = "P1501012"   # Andiroba 1.0x2.10             $21,206.12
_DOOR_ALU_BATIENTE = "P1501004"   # Aluminio y vidrio batiente     $2,283.73
_DOOR_ALU_CORREDIZA = "P1501005"  # Aluminio y vidrio corrediza    $419.48
_DOOR_POLIMETALICA = "P1501105"   # Polimetalica 0.70-0.90x2.10   $7,411.12
_DOOR_PVC = "P1502013"            # PVC blanca door tech           $9,181.12
_DOOR_CLOSET = "P1520002"         # Puerta despensa/ropa blanca    $611.62

# --- Floors ---
_FLOOR_PORCELANATO = "P0610001"   # Piso porcelanato interior      $1,660.86
_FLOOR_CERAMICA = "P06EE001"      # Piso ceramica area lavado      $1,214.66
_FLOOR_HORMIGON = "P0303150"      # H.A.B/Piso chapeado e=0.08    $650.61

# --- Wet areas ---
_WET_CERAMICA_BANO = "P08R1012"   # Revestimiento ceramica bano    $1,510.28
_WET_CERAMICA_LAVADO = "P08R1013" # Revestimiento ceramica lavado  $1,090.28
_WET_CERAMICA_COCINA = "P08R1014" # Revestimiento ceramica cocina  $1,510.28

# --- Kitchen / stairs ---
_KITCHEN_PARED = "P0609001"       # Gabinete cocina pared          $3,950
_KITCHEN_PISO = "P0609002"        # Gabinete cocina piso           $4,190
_ESCALONES = "P1201101"           # Escalones en escalera          $3,424.90
_BARANDA_ESC = "P1201301"         # Baranda escalera               $5,500


def _item_key_layer(takeoff: QuantityTakeoff) -> str:
    """Extract the CAD layer slug from item_key (e.g. 'json-wall-a-wall:volume' -> 'a-wall')."""
    key = takeoff.item_key.lower()
    for prefix in ("json-wall-", "json-door-", "json-window-"):
        if key.startswith(prefix):
            rest = key[len(prefix):]
            return rest.split(":")[0]
    return ""


def _input_thickness(takeoff: QuantityTakeoff) -> float | None:
    raw = takeoff.inputs.get("thickness_m")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    return None


def _input_block_name(takeoff: QuantityTakeoff) -> str:
    return str(takeoff.inputs.get("block_name") or "").strip()


def _wall_bc3_code(takeoff: QuantityTakeoff) -> str:
    """Select wall masonry code by thickness and material."""
    material = _material_hint(takeoff)
    if material == "concrete":
        return _WALL_CONCRETE

    thickness = _input_thickness(takeoff)
    if thickness is not None:
        if thickness <= 0.11:
            return _WALL_10CM
        if thickness <= 0.16:
            return _WALL_15CM_SNP
        return _WALL_20CM_BNP
    return _WALL_15CM_SNP


def _door_bc3_code(takeoff: QuantityTakeoff) -> str:
    """Select door code by block name, layer, and material hints."""
    block = _input_block_name(takeoff)
    layer = _item_key_layer(takeoff)
    material = _material_hint(takeoff)

    if "doble" in block.lower():
        return _DOOR_ANDIROBA_DBL
    if "ventana" in layer:
        return _DOOR_ALU_CORREDIZA
    if "closet" in layer:
        return _DOOR_CLOSET
    if material == "steel":
        return _DOOR_POLIMETALICA
    if material == "aluminum" or material == "aluminium":
        return _DOOR_ALU_BATIENTE
    if material == "pvc":
        return _DOOR_PVC
    return _DOOR_ANDIROBA_STD


def _floor_bc3_code(takeoff: QuantityTakeoff) -> str:
    """Select floor code by space type hints."""
    tags = _takeoff_tags(takeoff)
    layer = _item_key_layer(takeoff)
    if "lavado" in tags or "laundry" in tags or "lavado" in layer:
        return _FLOOR_CERAMICA
    return _FLOOR_PORCELANATO


def _wet_area_bc3_code(takeoff: QuantityTakeoff) -> str:
    """Select wet area code by space context."""
    tags = _takeoff_tags(takeoff)
    layer = _item_key_layer(takeoff)
    if "cocina" in tags or "kitchen" in tags or "cocina" in layer:
        return _WET_CERAMICA_COCINA
    if "lavado" in tags or "laundry" in tags:
        return _WET_CERAMICA_LAVADO
    return _WET_CERAMICA_BANO


def default_bc3_code_for_takeoff(takeoff: QuantityTakeoff) -> str | None:
    """Deterministic fallback: map item_type to a BC3 code from GIV00001 catalog.

    Uses CAD layer names, block names, thickness, and space hints to select
    the most specific catalog code available.
    """
    item_type = takeoff.item_type.lower()
    tags = _takeoff_tags(takeoff)

    # --- Walls ---
    if item_type in ("wall_volume", "wall_length", "wall_gross_area"):
        return _wall_bc3_code(takeoff)
    if item_type == "wall_finish_plaster":
        return _PLASTER_EXT if "exterior" in tags else _PLASTER_INT
    if item_type == "wall_finish_paint":
        return _PAINT_EXT if "exterior" in tags else _PAINT_INT
    if item_type == "wall_net_area":
        return _PLASTER_INT

    # --- Structural finish (plaster on columns / beams) ---
    if item_type.startswith("column_") and "finish" in item_type:
        return _PLASTER_COL
    if item_type.startswith("beam_") and "finish" in item_type:
        return _PLASTER_BEAM

    # --- Doors ---
    if item_type.startswith("door_"):
        return _door_bc3_code(takeoff)

    # --- Floors ---
    if item_type in ("floor_area", "floor_finish", "floor_finish_tile"):
        return _floor_bc3_code(takeoff)
    if item_type == "floor_screed":
        return _FLOOR_HORMIGON

    # --- Wet areas ---
    if item_type == "wet_area_fixture_count":
        return "P130CON"
    if item_type in ("wet_area_count", "wet_area_area", "wet_area_finish"):
        return _wet_area_bc3_code(takeoff)

    # --- Kitchen ---
    if item_type == "kitchen_count":
        return _KITCHEN_PARED
    if item_type == "kitchen_area":
        return _KITCHEN_PISO

    return _DEFAULT_BC3_MAP.get(item_type)


def chapter_path_for_takeoff(takeoff: QuantityTakeoff) -> list[ChapterSegment]:
    item_type = takeoff.item_type.lower()
    tags = _takeoff_tags(takeoff)

    if item_type == "wall_length":
        return [
            ChapterSegment("02", "ALBANILERIA"),
            ChapterSegment("02.01", "MUROS Y DIVISIONES"),
        ]

    if item_type == "structural_area":
        return [
            ChapterSegment("01", "ESTRUCTURA"),
            ChapterSegment("01.04", "SUPERFICIES ESTRUCTURALES"),
        ]

    if item_type == "pres_reference_line":
        disc = str(takeoff.inputs.get("pres_discipline", "") or "").upper()
        if "HORMIGON" in disc or "HORMIG" in disc:
            return [
                ChapterSegment("01", "ESTRUCTURA"),
                ChapterSegment("01.01", "HORMIGON ARMADO"),
            ]
        if "ACERO" in disc or "REFUERZO" in disc:
            return [
                ChapterSegment("01", "ESTRUCTURA"),
                ChapterSegment("01.03", "ACERO DE REFUERZO"),
            ]
        if "MURO" in disc or "DIVISION" in disc:
            return [
                ChapterSegment("02", "ALBANILERIA"),
                ChapterSegment("02.01", "MUROS Y DIVISIONES"),
            ]
        if "SUPERFICIE" in disc or "PANET" in disc or "PAÑET" in disc or "FRAGU" in disc:
            return [
                ChapterSegment("05", "TERMINACIONES"),
                ChapterSegment("05.01", "TERMINACION DE SUPERFICIES"),
            ]
        if "PISO" in disc or "PISOS" in disc:
            return [
                ChapterSegment("05", "TERMINACIONES"),
                ChapterSegment("05.02", "TERMINACION DE PISOS"),
            ]
        if "PUERTA" in disc:
            return [
                ChapterSegment("06", "CARPINTERIAS"),
                ChapterSegment("06.01", "PUERTAS"),
            ]
        if "PINTURA" in disc:
            return [
                ChapterSegment("05", "TERMINACIONES"),
                ChapterSegment("05.05", "PINTURA"),
            ]
        if "ELECTRIC" in disc or "ELECTR" in disc:
            return [
                ChapterSegment("08", "INSTALACIONES"),
                ChapterSegment("08.01", "ELECTRICAS"),
            ]
        if "SANIT" in disc or "PLOMER" in disc:
            return [
                ChapterSegment("08", "INSTALACIONES"),
                ChapterSegment("08.02", "SANITARIAS"),
            ]
        if "ESCAL" in disc:
            return [
                ChapterSegment("05", "TERMINACIONES"),
                ChapterSegment("05.06", "ESCALERAS"),
            ]
        short = disc[:40].strip() or "PARTIDAS PRES"
        return [
            ChapterSegment("07", "REFERENCIA PRESUPUESTO REAL"),
            ChapterSegment("07.01", short),
        ]

    if item_type.endswith("_waterproofing") or "waterproofing" in tags:
        return [
            ChapterSegment("04", "IMPERMEABILIZACION"),
            ChapterSegment("04.01", "TERMINACIONES HUMEDAS"),
        ]

    if item_type in {"stair_count"}:
        return [
            ChapterSegment("05", "TERMINACIONES"),
            ChapterSegment("05.06", "ESCALERAS"),
        ]

    if item_type in {"fixture_count"}:
        disc = str(takeoff.inputs.get("discipline") or "").lower()
        if disc == "plumbing":
            return [
                ChapterSegment("08", "INSTALACIONES"),
                ChapterSegment("08.02", "SANITARIAS"),
            ]
        return [
            ChapterSegment("08", "INSTALACIONES"),
            ChapterSegment("08.01", "ELECTRICAS"),
        ]

    if item_type in {"kitchen_count", "kitchen_area"}:
        return [
            ChapterSegment("05", "TERMINACIONES"),
            ChapterSegment("05.04", "COCINAS Y AREAS HUMEDAS"),
        ]

    if item_type.startswith(("beam_", "column_", "slab_", "footing_", "structural_")):
        if "formwork" in item_type:
            return [
                ChapterSegment("01", "ESTRUCTURA"),
                ChapterSegment("01.02", "ENCOFRADOS"),
            ]
        if "reinforcement_kg" in item_type:
            return [
                ChapterSegment("01", "ESTRUCTURA"),
                ChapterSegment("01.03", "ACERO DE REFUERZO"),
            ]
        if "reinforcement" in item_type:
            return [
                ChapterSegment("01", "ESTRUCTURA"),
                ChapterSegment("01.03", "ACERO DE REFUERZO"),
            ]
        if "count" in item_type or "length" in item_type:
            return [
                ChapterSegment("01", "ESTRUCTURA"),
                ChapterSegment("01.04", "ELEMENTOS ESTRUCTURALES"),
            ]
        return [
            ChapterSegment("01", "ESTRUCTURA"),
            ChapterSegment("01.01", "HORMIGON ARMADO"),
        ]

    if item_type.startswith("wall_"):
        if any(token in item_type for token in ("finish", "paint", "plaster")) or "finish" in tags:
            return [
                ChapterSegment("05", "TERMINACIONES"),
                ChapterSegment("05.01", "TERMINACION DE SUPERFICIES"),
            ]
        return [
            ChapterSegment("02", "ALBANILERIA"),
            ChapterSegment("02.01", "MUROS Y DIVISIONES"),
        ]

    if item_type.startswith("floor_"):
        if "wet_area" in tags or "waterproofing" in tags:
            return [
                ChapterSegment("04", "IMPERMEABILIZACION"),
                ChapterSegment("04.01", "TERMINACIONES HUMEDAS"),
            ]
        return [
            ChapterSegment("05", "TERMINACIONES"),
            ChapterSegment("05.02", "TERMINACION DE PISOS"),
        ]

    if item_type.startswith("ceiling_"):
        return [
            ChapterSegment("05", "TERMINACIONES"),
            ChapterSegment("05.03", "TECHOS Y CIELOS"),
        ]

    if item_type.startswith("door_"):
        return [
            ChapterSegment("06", "CARPINTERIAS"),
            ChapterSegment("06.01", "PUERTAS"),
        ]

    if item_type.startswith("window_"):
        return [
            ChapterSegment("06", "CARPINTERIAS"),
            ChapterSegment("06.02", "VENTANAS"),
        ]

    if item_type == "wet_area_fixture_count":
        return [
            ChapterSegment("08", "INSTALACIONES"),
            ChapterSegment("08.02", "SANITARIAS"),
        ]

    if item_type.startswith("wet_area_"):
        if "waterproofing" in item_type or "waterproofing" in tags:
            return [
                ChapterSegment("04", "IMPERMEABILIZACION"),
                ChapterSegment("04.01", "TERMINACIONES HUMEDAS"),
            ]
        return [
            ChapterSegment("05", "TERMINACIONES"),
            ChapterSegment("05.04", "TERMINACIONES HUMEDAS"),
        ]

    return [
        ChapterSegment("99", "PARTIDAS GENERALES"),
        ChapterSegment("99.01", "ITEMS POR CLASIFICAR"),
    ]


def _structural_summary(takeoff: QuantityTakeoff) -> str:
    item_type = takeoff.item_type.lower()
    material_hint = _material_hint(takeoff)

    if item_type == "beam_concrete_volume":
        return "Hormigon armado en vigas"
    if item_type == "column_concrete_volume":
        return "Hormigon armado en columnas"
    if item_type == "slab_concrete_volume":
        return "Hormigon armado en losas"
    if item_type == "footing_concrete_volume":
        return "Hormigon armado en zapatas"
    if item_type == "beam_formwork_area_hint":
        return "Encofrado de vigas"
    if item_type == "column_formwork_area_hint":
        return "Encofrado de columnas"
    if item_type == "slab_formwork_area_hint":
        return "Encofrado inferior de losas"
    if item_type == "footing_formwork_area_hint":
        return "Encofrado de zapatas"
    if item_type == "beam_reinforcement_kg":
        return "Acero de refuerzo en vigas"
    if item_type == "column_reinforcement_kg":
        return "Acero de refuerzo en columnas"
    if item_type == "slab_reinforcement_kg":
        return "Acero de refuerzo en losas"
    if item_type == "footing_reinforcement_kg":
        return "Acero de refuerzo en zapatas"
    if item_type == "beam_volume":
        return "Volumen estructural de vigas"
    if item_type == "column_volume":
        return "Volumen estructural de columnas"
    if item_type == "slab_volume":
        return "Volumen estructural de losas"
    if item_type == "footing_volume":
        return "Volumen estructural de zapatas"
    if item_type == "beam_area":
        return "Area de vigas"
    if item_type == "column_area":
        return "Area de columnas"
    if item_type == "slab_area":
        return "Area de losas"
    if item_type == "footing_area":
        return "Area de zapatas"
    if item_type == "beam_length":
        return "Longitud de vigas"
    if item_type == "column_length":
        return "Longitud de columnas"
    if item_type == "beam_count":
        return "Cantidad de vigas"
    if item_type == "column_count":
        return "Cantidad de columnas"
    if item_type == "slab_count":
        return "Cantidad de losas"
    if item_type == "footing_count":
        return "Cantidad de zapatas"
    if item_type == "structural_count":
        return "Elementos estructurales"
    if item_type == "structural_length":
        return "Longitud estructural"
    if item_type == "structural_volume":
        return "Volumen estructural"
    if material_hint == "concrete":
        return "Elemento estructural de hormigon"
    return "Elemento estructural"


def _wall_summary(takeoff: QuantityTakeoff) -> str:
    item_type = takeoff.item_type.lower()
    tags = _takeoff_tags(takeoff)
    material_hint = _material_hint(takeoff)
    layer = _item_key_layer(takeoff)
    thickness = _input_thickness(takeoff)

    if item_type == "wall_waterproofing":
        return "Impermeabilizante en muros areas humedas"
    if item_type == "wall_finish_paint":
        if "exterior" in tags:
            return "Pintura acrilica muros exteriores"
        return "Pintura acrilica muros interiores"
    if item_type == "wall_finish_plaster":
        if "exterior" in tags:
            return "Panete liso en muros exteriores e=2.00cm"
        return "Panete liso en muros interiores e=1.75cm"
    if item_type == "wall_finish_tile":
        return "Revestimiento ceramica en muros"
    if item_type == "wall_net_area":
        return "Panete liso en muros interiores e=1.75cm"

    # Wall volume/length/area: differentiate by thickness and layer
    if item_type in ("wall_volume", "wall_length", "wall_gross_area", "wall_area"):
        if material_hint == "concrete":
            return "Muro de hormigon armado e=0.15m"

        size_label = "15x20x40"
        kind = "SNP"
        if thickness is not None:
            if thickness <= 0.11:
                size_label = "10x20x40"
                kind = "SNP"
            elif thickness <= 0.16:
                size_label = "15x20x40"
                kind = "SNP"
            else:
                size_label = "20x20x40"
                kind = "BNP"

        layer_tag = ""
        if layer and layer not in ("a-wall", "muros", "muro", "muross"):
            layer_tag = f" (capa {layer.upper()})"

        return f"Muro bloques {size_label} {kind}{layer_tag}"

    return "Muro de bloques 15x20x40 SNP"


def _floor_summary(takeoff: QuantityTakeoff) -> str:
    item_type = takeoff.item_type.lower()
    tags = _takeoff_tags(takeoff)
    layer = _item_key_layer(takeoff)

    if item_type == "floor_waterproofing" or "waterproofing" in tags:
        return "Impermeabilizante en pisos areas humedas"
    if item_type == "floor_screed":
        return "Base de piso hormigon chapeado e=0.08"
    if "lavado" in tags or "laundry" in tags or "lavado" in layer:
        return "Piso ceramica area lavado"
    return "Piso porcelanato interior apartamento"


def _ceiling_summary(takeoff: QuantityTakeoff) -> str:
    item_type = takeoff.item_type.lower()
    if item_type == "ceiling_finish_paint":
        return "Pintura economica losas y vigas"
    if item_type in ("ceiling_area", "ceiling_finish_plaster"):
        return "Panete liso en losa de techo"
    return "Panete liso en losa de techo"


def _door_summary(takeoff: QuantityTakeoff) -> str:
    item_type = takeoff.item_type.lower()
    material_hint = _material_hint(takeoff)
    block = _input_block_name(takeoff)
    layer = _item_key_layer(takeoff)

    if item_type == "door_hardware_set":
        return "Juego herrajes puerta"
    if item_type == "door_frame_count":
        return "Puerta aluminio y vidrio batiente"

    if "doble" in block.lower():
        return "Puerta andiroba pintura natural (1.0x2.10) batiente"
    if "ventana" in layer:
        return "Puerta corrediza aluminio y vidrio"
    if "closet" in layer:
        return "Puerta madera despensa y ropa blanca"
    if material_hint == "steel":
        return "Puerta polimetalica (0.90x2.10) batiente"
    if material_hint == "pvc":
        return "Puerta PVC blanca tipo door tech (0.90x2.10)"
    if material_hint == "aluminum":
        return "Puerta aluminio y vidrio batiente"
    if item_type == "door_leaf_metal_count":
        return "Puerta polimetalica (0.90x2.10) batiente"
    return "Puerta andiroba pintura natural (0.90x2.10) batiente"


def _window_summary(takeoff: QuantityTakeoff) -> str:
    item_type = takeoff.item_type.lower()
    if item_type == "window_installation_count":
        return "Ventana corredera aluminio y vidrio"
    if item_type == "window_sealant_area":
        return "Sellado y tratamiento de ventanas"
    return "Ventana corredera aluminio y vidrio"


def _fixture_count_summary(takeoff: QuantityTakeoff) -> str:
    """Human-readable summary for vision-derived fixtures (electrical / plumbing / exterior)."""
    disc = str(takeoff.inputs.get("discipline") or "").lower()
    ftype = str(takeoff.inputs.get("fixture_type") or "").lower()
    loc = str(takeoff.inputs.get("location_hint") or "").strip()
    loc_part = f" ({loc})" if loc else ""

    if disc == "electrical" or disc == "electric":
        labels = {
            "outlet_110v": "Tomacorrientes 110V",
            "outlet_220v": "Tomacorrientes 220V",
            "switch_single": "Interruptores sencillos",
            "switch_double": "Interruptores dobles",
            "switch_triple": "Interruptores triples",
            "switch_dimmer": "Dimmer",
            "luminaire_ceiling": "Luminarias de techo",
            "luminaire_wall": "Luminarias de pared",
            "luminaire_recessed": "Luminarias empotradas",
            "panel_breaker": "Tablero / breaker",
            "emergency_light": "Luz de emergencia",
            "data_outlet": "Punto de datos",
            "fan_connection": "Conexion ventilador",
            "ac_connection": "Conexion aire acondicionado",
        }
        base = labels.get(ftype, f"Punto electrico ({ftype or 'tipo no especificado'})")
        return f"{base}{loc_part}"

    if disc == "plumbing":
        labels = {
            "water_supply_point": "Punto suministro agua (tuberia)",
            "drain_point": "Punto desague / drenaje",
            "vent_pipe": "Tuberia de ventilacion",
            "cleanout": "Registro / cleanout",
            "floor_drain": "Sumidero de piso",
            "pump": "Bomba",
            "gas_distribution": "Distribucion gas",
        }
        base = labels.get(ftype, f"Punto sanitario / plomeria ({ftype or 'tipo no especificado'})")
        return f"{base}{loc_part}"

    if disc == "exterior":
        return f"Trabajo exterior / sitio ({ftype or 'elemento'}){loc_part}"

    return f"Equipo / accesorio ({ftype or 'fixture'}){loc_part}"


def _wet_area_summary(takeoff: QuantityTakeoff) -> str:
    item_type = takeoff.item_type.lower()
    tags = _takeoff_tags(takeoff)
    layer = _item_key_layer(takeoff)

    if item_type == "wet_area_fixture_count":
        ft = str(takeoff.inputs.get("fixture_type") or "").replace("_", " ").strip()
        at = str(takeoff.inputs.get("area_type") or "").replace("_", " ").strip()
        if ft and at:
            return f"Pieza sanitaria ({ft}) en {at}"
        return "Pieza sanitaria en área húmeda"

    if "waterproofing" in item_type:
        return "Impermeabilizante en areas humedas"
    if "cocina" in tags or "kitchen" in tags or "cocina" in layer:
        return "Revestimiento ceramica en cocina"
    if "lavado" in tags or "laundry" in tags:
        return "Revestimiento ceramica area lavado"
    return "Revestimiento ceramica en bano"


_GENERIC_CAD_TOKENS: tuple[str, ...] = (
    "capa CAD",
    "json-beam",
    "json-column",
    "json-slab",
    "json-footing",
    "json-wall",
    "xref",
    "hatch ",
    "layer 0",
    "no identificado",
    "tipo no identificado",
)


def _is_generic_cad_label(text: str) -> bool:
    if not text:
        return True
    lowered = text.lower()
    return any(token.lower() in lowered for token in _GENERIC_CAD_TOKENS)


def build_budget_summary(
    takeoff: QuantityTakeoff,
    candidate: BudgetCandidate | None = None,
) -> str:
    item_type = takeoff.item_type.lower()
    if item_type == "pres_reference_line":
        summary = str(takeoff.inputs.get("pres_summary", "") or "").strip()
        return append_provenance(summary or takeoff.item_key, takeoff)

    llm_summary = ""
    if candidate is not None and candidate.source == "partida_generator":
        llm_summary = candidate.summary.strip()
        if llm_summary and not _is_generic_cad_label(llm_summary):
            return append_provenance(llm_summary, takeoff)

    specific = str(takeoff.inputs.get("takeoff_description") or "").strip()
    if specific and not _is_generic_cad_label(specific):
        return append_provenance(specific, takeoff)

    if llm_summary:
        return append_provenance(llm_summary, takeoff)

    if candidate is not None:
        candidate_summary = candidate.summary.strip()
        if candidate_summary:
            return append_provenance(candidate_summary, takeoff)
    if specific:
        return append_provenance(specific, takeoff)
    if item_type == "structural_area":
        return append_provenance("Superficie estructural (referencia)", takeoff)

    if item_type.startswith(("beam_", "column_", "slab_", "structural_")):
        return append_provenance(_structural_summary(takeoff), takeoff)
    if item_type.startswith("wall_"):
        return append_provenance(_wall_summary(takeoff), takeoff)
    if item_type.startswith("floor_"):
        return append_provenance(_floor_summary(takeoff), takeoff)
    if item_type.startswith("ceiling_"):
        return append_provenance(_ceiling_summary(takeoff), takeoff)
    if item_type.startswith("door_"):
        return append_provenance(_door_summary(takeoff), takeoff)
    if item_type.startswith("window_"):
        return append_provenance(_window_summary(takeoff), takeoff)
    if item_type.startswith("wet_area_"):
        return append_provenance(_wet_area_summary(takeoff), takeoff)

    if item_type == "kitchen_count":
        return append_provenance("Gabinete de cocina", takeoff)
    if item_type == "kitchen_area":
        return append_provenance("Gabinete de cocina", takeoff)
    if item_type == "stair_count":
        return append_provenance("Escalones en escalera", takeoff)
    if item_type == "fixture_count":
        if takeoff.inputs.get("discipline") or takeoff.inputs.get("fixture_type"):
            return append_provenance(_fixture_count_summary(takeoff), takeoff)
        return append_provenance("Juego accesorios de banos", takeoff)

    return append_provenance(takeoff.item_type.replace("_", " ").strip().capitalize(), takeoff)


def _decomposition_parent_sort_key(code: str) -> tuple[int, str]:
    """Prefer chapter-style codes (e.g. A.024ASA04) over typology roots (TGIU…)."""
    c = code.strip()
    if c.startswith("TGIU") or (c.startswith("TG") and len(c) <= 10):
        return (2, c)
    if "." in c and c[:1].isalpha():
        return (0, c)
    return (1, c)


def _pick_decomposition_parent(parents: list[str], *, chapter_codes: set[str]) -> str | None:
    if not parents:
        return None
    if len(parents) == 1:
        return parents[0]
    in_chapter = [p for p in parents if p in chapter_codes]
    pool = in_chapter if in_chapter else list(parents)
    return min(pool, key=_decomposition_parent_sort_key)


def _segment_title_for_bc3_code(bc3_catalog: dict[str, Any], code: str) -> str:
    concepts = bc3_catalog.get("concepts_by_code") or {}
    row = concepts.get(code) or {}
    summary = str(row.get("summary") or "").strip()
    if summary:
        return summary
    texts = bc3_catalog.get("texts") or {}
    long_t = str(texts.get(code) or "").strip()
    if long_t:
        clip = 120
        return long_t[:clip] + ("..." if len(long_t) > clip else "")
    return code


def chapter_path_from_bc3_catalog(
    bc3_catalog: dict[str, Any],
    resolved_bc3_code: str,
    *,
    max_depth: int = 32,
) -> list[ChapterSegment] | None:
    """
    Build chapter folders from ~D decomposition in the BC3 catalog (root → leaf parent).

    When ``context.metadata["use_bc3_catalog_chapters"]`` is true, the composer can use this
    instead of the fixed Dupla chapter map so grouping follows the example BC3 hierarchy.
    """
    code = (resolved_bc3_code or "").strip()
    if not code or not bc3_catalog:
        return None

    parent_map: dict[str, list[str]] = bc3_catalog.get("decomposition_parent_candidates") or {}
    if not parent_map:
        return None

    chapters_list = bc3_catalog.get("chapters") or []
    chapter_codes = {str(c.get("code", "")).strip() for c in chapters_list if c.get("code")}

    tip_to_root: list[str] = []
    current = code
    visited: set[str] = set()

    while len(tip_to_root) < max_depth:
        parents = parent_map.get(current) or []
        if not parents:
            break
        parent = _pick_decomposition_parent(parents, chapter_codes=chapter_codes)
        if not parent or parent == current:
            break
        if parent in visited:
            break
        visited.add(parent)
        tip_to_root.append(parent)
        current = parent

    if not tip_to_root:
        return None

    ordered = list(reversed(tip_to_root))
    return [ChapterSegment(seg_code, _segment_title_for_bc3_code(bc3_catalog, seg_code)) for seg_code in ordered]
