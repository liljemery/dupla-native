import re

def parse_location_from_filename(filename: str) -> tuple[str | None, str | None]:
    """
    Extracts the building block and level from a given filename.
    Returns a tuple of (building_block, level_id).
    
    Examples:
        - "Bloque_A_Nivel_1.pdf" -> ("Bloque A", "Nivel 1")
        - "Torre B Nivel 3.dwg" -> ("Torre B", "Nivel 3")
        - "planta_arquitectonica.pdf" -> (None, None)
    """
    block_pattern = re.compile(r'(?i)(bloque|torre|edificio)[\s_-]*([A-Z0-9]+)')
    level_pattern = re.compile(r'(?i)(nivel|piso|planta)[\s_-]*([A-Z0-9]+)')
    
    block_match = block_pattern.search(filename)
    level_match = level_pattern.search(filename)
    
    building_block = None
    if block_match:
        building_block = f"{block_match.group(1).capitalize()} {block_match.group(2).upper()}"
        
    level_id = None
    if level_match:
        level_id = f"{level_match.group(1).capitalize()} {level_match.group(2).upper()}"
        
    return building_block, level_id
