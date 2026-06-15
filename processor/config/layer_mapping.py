"""
Configuración del sistema de automatización CAD.
Define nomenclatura de disciplinas, factores de conversión de unidades,
y parámetros globales del procesamiento.
"""

import re
from pathlib import Path
from typing import Optional

from .models import DisciplineCode, UnitSystem


# ============================================================================
# NOMENCLATURA DE DISCIPLINAS (Estándar NCS/AIA)
# ============================================================================
# Mapeo: prefijo de capa → código de disciplina
# Ejemplo: capa "A-WALL-FULL" → prefijo "A" → DisciplineCode.A (Arquitectura)

DISCIPLINE_PREFIX_MAP: dict[str, DisciplineCode] = {
    "A":  DisciplineCode.A,   # Arquitectura
    "S":  DisciplineCode.S,   # Estructural
    "M":  DisciplineCode.M,   # Mecánico / HVAC
    "E":  DisciplineCode.E,   # Eléctrico
    "P":  DisciplineCode.P,   # Plomería
    "C":  DisciplineCode.C,   # Civil
    "F":  DisciplineCode.F,   # Protección contra incendios
    "G":  DisciplineCode.G,   # General
    "L":  DisciplineCode.L,   # Paisajismo
    "T":  DisciplineCode.T,   # Telecomunicaciones
    "I":  DisciplineCode.I,   # Interiorismo
    "Q":  DisciplineCode.Q,   # Equipamiento
}

# Prefijos alternativos / variantes comunes
DISCIPLINE_ALIAS_MAP: dict[str, DisciplineCode] = {
    "AR":   DisciplineCode.A,   # Arquitectura (variante)
    "ARQ":  DisciplineCode.A,   # Arquitectura (español)
    "ST":   DisciplineCode.S,   # Estructural (variante)
    "EST":  DisciplineCode.S,   # Estructural (español)
    "ME":   DisciplineCode.M,   # Mecánico (variante)
    "MEC":  DisciplineCode.M,   # Mecánico (español)
    "EL":   DisciplineCode.E,   # Eléctrico (variante)
    "ELE":  DisciplineCode.E,   # Eléctrico (español)
    "PL":   DisciplineCode.P,   # Plomería (variante)
    "PLO":  DisciplineCode.P,   # Plomería (español)
    "CI":   DisciplineCode.C,   # Civil (variante)
    "CIV":  DisciplineCode.C,   # Civil (español)
    "FA":   DisciplineCode.F,   # Fire Alarm
    "FS":   DisciplineCode.F,   # Fire Sprinkler
    "FP":   DisciplineCode.F,   # Fire Protection
    "SE":   DisciplineCode.E,   # Security → Eléctrico
    "TE":   DisciplineCode.T,   # Telecom (variante)
    "HVAC": DisciplineCode.M,   # HVAC explícito
    "SS":   DisciplineCode.P,   # Sanitary Sewer
    "SD":   DisciplineCode.P,   # Storm Drain
}

# Capas que se consideran "comunes" y se incluyen en todas las disciplinas
COMMON_LAYERS: set[str] = {
    "0",
    "DEFPOINTS",
    "ASHADE",
}

# Patrones de capas comunes (regex) — se incluyen en todos los archivos separados
COMMON_LAYER_PATTERNS: list[str] = [
    r"^G[-_]",           # General: G-GRID, G-ANNO, G-TITL
    r"^0$",              # Capa 0
    r"^DEFPOINTS$",      # Defpoints
    r"^BORDER",          # Bordes
    r"^TITLE",           # Títulos
    r"^VIEWPORT",        # Viewports
    r"^XREF",            # Referencias externas
    r"^ASHADE$",         # Shade
]


# ============================================================================
# FACTORES DE CONVERSIÓN DE UNIDADES
# ============================================================================
# Todos los factores convierten a MILÍMETROS (unidad target por defecto)

UNIT_TO_MM: dict[UnitSystem, float] = {
    UnitSystem.UNITLESS:     1.0,        # Asumimos mm si no hay unidad
    UnitSystem.INCHES:       25.4,
    UnitSystem.FEET:         304.8,
    UnitSystem.MILES:        1_609_344.0,
    UnitSystem.MILLIMETERS:  1.0,
    UnitSystem.CENTIMETERS:  10.0,
    UnitSystem.METERS:       1000.0,
    UnitSystem.KILOMETERS:   1_000_000.0,
    UnitSystem.MICROINCHES:  0.0000254,
    UnitSystem.MILS:         0.0254,
    UnitSystem.YARDS:        914.4,
    UnitSystem.DECIMETERS:   100.0,
    UnitSystem.DECAMETERS:   10_000.0,
    UnitSystem.HECTOMETERS:  100_000.0,
}

# Mapeo inverso: valor de $INSUNITS → UnitSystem
INSUNITS_MAP: dict[int, UnitSystem] = {unit.value: unit for unit in UnitSystem}

# Unidad objetivo del sistema
TARGET_UNIT: UnitSystem = UnitSystem.MILLIMETERS


# ============================================================================
# CONFIGURACIÓN DEL SISTEMA
# ============================================================================

# Extensiones de archivo soportadas
SUPPORTED_EXTENSIONS: set[str] = {".dxf", ".dwg"}

# Directorio de salida por defecto (relativo al directorio de los archivos)
DEFAULT_OUTPUT_DIR: str = "cad_output"

# Subdirectorios de salida
OUTPUT_SUBDIRS: dict[str, str] = {
    "disciplines": "por_disciplina",
    "normalized": "normalizados",
    "split": "planos_separados",
    "reports": "reportes",
}

# Formato del reporte
REPORT_SEPARATOR = "=" * 80
REPORT_SUBSEPARATOR = "-" * 60


# ============================================================================
# FUNCIONES DE CONFIGURACIÓN
# ============================================================================

def classify_layer(layer_name: str) -> DisciplineCode:
    """
    Clasifica una capa por su nombre usando la nomenclatura de disciplinas.
    
    Estrategia de búsqueda:
    1. Busca en prefijos estándar NCS (A, S, M, E, P, etc.)
    2. Busca en aliases / variantes
    3. Si no coincide → UNKNOWN
    
    Args:
        layer_name: Nombre de la capa (ej: "A-WALL-FULL")
    
    Returns:
        DisciplineCode correspondiente
    """
    name_upper = layer_name.upper().strip()
    
    # Verificar si es capa común
    if is_common_layer(name_upper):
        return DisciplineCode.G
    
    # Extraer prefijo: todo antes del primer separador (- o _)
    match = re.match(r"^([A-Z]+)[-_]", name_upper)
    if match:
        prefix = match.group(1)
        
        # Buscar en prefijos estándar (1 carácter primero)
        if len(prefix) >= 1 and prefix[0] in DISCIPLINE_PREFIX_MAP:
            return DISCIPLINE_PREFIX_MAP[prefix[0]]
        
        # Buscar en aliases (prefijos multi-carácter)
        if prefix in DISCIPLINE_ALIAS_MAP:
            return DISCIPLINE_ALIAS_MAP[prefix]
    
    # Buscar por contenido para capas sin formato estándar
    for alias, discipline in DISCIPLINE_ALIAS_MAP.items():
        if name_upper.startswith(alias):
            return DISCIPLINE_ALIAS_MAP[alias]
    
    return DisciplineCode.UNKNOWN


def is_common_layer(layer_name: str) -> bool:
    """Determina si una capa es 'común' (debe incluirse en todas las disciplinas)."""
    name_upper = layer_name.upper().strip()
    
    if name_upper in COMMON_LAYERS:
        return True
    
    for pattern in COMMON_LAYER_PATTERNS:
        if re.match(pattern, name_upper):
            return True
    
    return False


def get_conversion_factor(from_unit: UnitSystem, to_unit: Optional[UnitSystem] = None) -> float:
    """
    Calcula el factor de conversión entre dos sistemas de unidades.
    
    Args:
        from_unit: Unidad de origen
        to_unit: Unidad de destino (por defecto: TARGET_UNIT)
    
    Returns:
        Factor multiplicador para convertir coordenadas
    """
    if to_unit is None:
        to_unit = TARGET_UNIT
    
    if from_unit == to_unit:
        return 1.0
    
    # Convertir: from → mm → to
    from_to_mm = UNIT_TO_MM.get(from_unit, 1.0)
    to_to_mm = UNIT_TO_MM.get(to_unit, 1.0)
    
    return from_to_mm / to_to_mm


def get_output_dir(source_path: Path, subdir_key: str = "disciplines") -> Path:
    """Genera la ruta del directorio de salida."""
    base = source_path.parent / DEFAULT_OUTPUT_DIR
    subdir = OUTPUT_SUBDIRS.get(subdir_key, "")
    if subdir:
        return base / subdir
    return base
