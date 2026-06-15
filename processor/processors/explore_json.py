"""
Diagnostic script to explore the structure of resultados_model_derivative.json
Finds sample objects of each type to understand where data lives.
"""
import json
import sys

json_path = r"c:\Users\chris\Documents\Dupla\resultados_model_derivative.json"

print(f"Loading {json_path}...")
with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Get collection
collection = []
if isinstance(data, dict):
    if "views" in data:
        for view in data.get("views", []):
            collection.extend(view.get("objects", []))
    elif "data" in data and "collection" in data["data"]:
        collection = data["data"]["collection"]
elif isinstance(data, list):
    collection = data

print(f"Total objects: {len(collection)}")
print()

# === STEP 1: Show structure of a few objects ===
print("=" * 80)
print("STEP 1: First 3 objects - full structure keys")
print("=" * 80)
for i, obj in enumerate(collection[:3]):
    print(f"\n--- Object {i} ---")
    print(f"  Top-level keys: {list(obj.keys())}")
    print(f"  name: {obj.get('name', 'N/A')}")
    props = obj.get("properties", {})
    print(f"  properties categories: {list(props.keys())}")
    for cat, cat_props in props.items():
        if isinstance(cat_props, dict):
            print(f"    [{cat}]: {list(cat_props.keys())[:10]}")

# === STEP 2: Find the "Name " property (with space) in General ===
print()
print("=" * 80)
print("STEP 2: Checking properties > General > 'Name ' field for entity types")
print("=" * 80)

type_counts = {}
samples_by_type = {}

for obj in collection:
    props = obj.get("properties", {})
    
    # Check General category for "Name " (with trailing space)
    general = props.get("General", {})
    entity_type = None
    
    # Try various key patterns
    for key in general:
        if key.strip().lower() == "name":
            entity_type = general[key]
            break
    
    if not entity_type:
        # Try other categories
        for cat, cat_props in props.items():
            if isinstance(cat_props, dict):
                for key in cat_props:
                    if key.strip().lower() == "name":
                        entity_type = cat_props[key]
                        break
            if entity_type:
                break
    
    if not entity_type:
        entity_type = obj.get("name", "Unknown")
    
    type_str = str(entity_type)
    type_counts[type_str] = type_counts.get(type_str, 0) + 1
    
    if type_str not in samples_by_type:
        samples_by_type[type_str] = obj

print("\nEntity types found via properties > * > Name:")
for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"  {t}: {c}")

# === STEP 3: Find Hatches ===
print()
print("=" * 80)
print("STEP 3: Sample HATCH objects (full properties)")
print("=" * 80)

hatch_count = 0
for obj in collection:
    props = obj.get("properties", {})
    general = props.get("General", {})
    
    entity_name = None
    for key in general:
        if key.strip().lower() == "name":
            entity_name = str(general[key]).lower()
            break
    
    if entity_name and "hatch" in entity_name:
        hatch_count += 1
        if hatch_count <= 3:
            print(f"\n--- Hatch #{hatch_count} ---")
            print(f"  obj['name'] = {obj.get('name', 'N/A')}")
            print(f"  Full properties:")
            print(json.dumps(props, indent=4, ensure_ascii=False))
        if hatch_count >= 3:
            break

if hatch_count == 0:
    print("  No hatches found via General > Name")

# === STEP 4: Find Dimensions ===
print()
print("=" * 80)
print("STEP 4: Sample DIMENSION objects (full properties)")
print("=" * 80)

dim_count = 0
for obj in collection:
    props = obj.get("properties", {})
    general = props.get("General", {})
    
    entity_name = None
    for key in general:
        if key.strip().lower() == "name":
            entity_name = str(general[key]).lower()
            break
    
    if entity_name and "dimension" in entity_name:
        dim_count += 1
        if dim_count <= 3:
            print(f"\n--- Dimension #{dim_count} ---")
            print(f"  obj['name'] = {obj.get('name', 'N/A')}")
            print(f"  Full properties:")
            print(json.dumps(props, indent=4, ensure_ascii=False))
        if dim_count >= 3:
            break

if dim_count == 0:
    print("  No dimensions found via General > Name")

# === STEP 5: Find Block References ===
print()
print("=" * 80)
print("STEP 5: Sample BLOCK REFERENCE objects (full properties)")
print("=" * 80)

block_count = 0
for obj in collection:
    props = obj.get("properties", {})
    general = props.get("General", {})
    
    entity_name = None
    for key in general:
        if key.strip().lower() == "name":
            entity_name = str(general[key]).lower()
            break
    
    if entity_name and ("block reference" in entity_name or "insert" in entity_name):
        block_count += 1
        if block_count <= 3:
            print(f"\n--- Block Reference #{block_count} ---")
            print(f"  obj['name'] = {obj.get('name', 'N/A')}")
            print(f"  Full properties:")
            print(json.dumps(props, indent=4, ensure_ascii=False))
        if block_count >= 3:
            break

if block_count == 0:
    print("  No block references found via General > Name")

# === STEP 6: Find Text / MText ===
print()
print("=" * 80)
print("STEP 6: Sample TEXT/MTEXT objects (full properties)")
print("=" * 80)

text_count = 0
mtext_count = 0
for obj in collection:
    props = obj.get("properties", {})
    general = props.get("General", {})
    name_lower = obj.get("name", "").lower()
    
    entity_name = None
    for key in general:
        if key.strip().lower() == "name":
            entity_name = str(general[key]).lower()
            break
    
    is_text = (entity_name and entity_name.strip() == "text") or ("text" in name_lower and "mtext" not in name_lower)
    is_mtext = (entity_name and "mtext" in entity_name) or ("mtext" in name_lower)
    
    if is_text and text_count < 3:
        text_count += 1
        print(f"\n--- Text #{text_count} ---")
        print(f"  obj['name'] = {obj.get('name', 'N/A')}")
        print(f"  Full properties:")
        print(json.dumps(props, indent=4, ensure_ascii=False))
    
    if is_mtext and mtext_count < 3:
        mtext_count += 1
        print(f"\n--- MText #{mtext_count} ---")
        print(f"  obj['name'] = {obj.get('name', 'N/A')}")
        print(f"  Full properties:")
        print(json.dumps(props, indent=4, ensure_ascii=False))
    
    if text_count >= 3 and mtext_count >= 3:
        break

# === STEP 7: What does obj['name'] look like for Entities? ===
print()
print("=" * 80)
print("STEP 7: obj['name'] values for objects classified as Entity by name alone")
print("=" * 80)

entity_names = {}
for obj in collection:
    name = str(obj.get("name", ""))
    name_lower = name.lower()
    
    # Use the same logic as the processor
    obj_type = "Entity"
    if "line" in name_lower and "polyline" not in name_lower:
        obj_type = "Line"
    elif "polyline" in name_lower:
        obj_type = "Polyline"
    elif "hatch" in name_lower:
        obj_type = "Hatch"
    elif "text" in name_lower and "mtext" not in name_lower:
        obj_type = "Text"
    elif "mtext" in name_lower:
        obj_type = "MText"
    elif "dimension" in name_lower:
        obj_type = "Dimension"
    elif "block reference" in name_lower or "insert" in name_lower:
        obj_type = "Block Reference"
    
    if obj_type == "Entity":
        entity_names[name] = entity_names.get(name, 0) + 1

print("Unique obj['name'] values for 'Entity' objects:")
for n, c in sorted(entity_names.items(), key=lambda x: -x[1]):
    print(f"  '{n}': {c}")

print("\nDone!")
