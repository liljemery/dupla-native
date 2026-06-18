import os
import subprocess
import shutil
import zipfile

PROJECT_DIR = os.path.join(os.path.dirname(__file__), "DuplaExtractor")
BUNDLE_DIR = os.path.join(os.path.dirname(__file__), "DuplaExtractor.bundle")
OUTPUT_ZIP = os.path.join(os.path.dirname(__file__), "DuplaExtractor.zip")

# NOTE: the C# source lives in DuplaExtractor/Commands.cs ON DISK and is the
# source of truth (it emits Vertices / Line Start-End so the GeometryMerger can
# collapse double-line walls — P2.7). This script no longer regenerates it; an
# older embedded copy used to overwrite it and silently drop the vertices.

PACKAGE_XML = """<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0" AppVersion="1.0" Author="Dupla" Name="DuplaExtractor" Description="Extrae datos de bloques y polilineas a JSON">
  <Components>
    <RuntimeRequirements OS="Win64" Platform="AutoCAD" SeriesMin="R24.0" SeriesMax="R24.3" />
    <ComponentEntry AppName="DuplaExtractor" Version="1.0" ModuleName="./Contents/DuplaExtractor.dll" AppDescription="Extractor de cantidades" LoadOnAutoCADStartup="true" />
  </Components>
</ApplicationPackage>
"""

def create_bundle():
    commands_cs = os.path.join(PROJECT_DIR, "Commands.cs")
    if not os.path.exists(commands_cs):
        raise FileNotFoundError(
            f"Falta {commands_cs}. El fuente C# en disco es la fuente de verdad; "
            "no se regenera desde este script."
        )
    print("1. Usando el Commands.cs en disco (con vertices) — no se regenera.")

    print("2. Compilando el DLL (descargando librerías de Autodesk)...")
    subprocess.run(["dotnet", "build", "-c", "Release"], cwd=PROJECT_DIR, check=True)

    print("3. Preparando la carpeta .bundle...")
    if os.path.exists(BUNDLE_DIR):
        shutil.rmtree(BUNDLE_DIR)
    os.makedirs(os.path.join(BUNDLE_DIR, "Contents"))
    
    with open(os.path.join(BUNDLE_DIR, "PackageContents.xml"), "w", encoding="utf-8") as f:
        f.write(PACKAGE_XML)
        
    # Copiar el DLL compilado y sus dependencias (ej. System.Text.Json)
    release_dir = os.path.join(PROJECT_DIR, "bin", "Release", "net48")
    for file_name in os.listdir(release_dir):
        if file_name.endswith(".dll"):
            lower_name = file_name.lower()
            # Ignorar dlls de autocad en el paquete final (por si acaso el ExcludeAssets no los limpia del todo)
            if not lower_name.startswith("ac") and not lower_name.startswith("ad") and not lower_name.startswith("autocad"):
                shutil.copy(os.path.join(release_dir, file_name), os.path.join(BUNDLE_DIR, "Contents"))
    
    print("4. Comprimiendo en formato ZIP para la nube...")
    with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(BUNDLE_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                # Ruta relativa dentro del ZIP
                arcname = os.path.relpath(file_path, os.path.dirname(BUNDLE_DIR))
                zipf.write(file_path, arcname)
                
    print(f"[OK] Plugin C# compilado y empaquetado como '{os.path.basename(OUTPUT_ZIP)}'!")

if __name__ == "__main__":
    create_bundle()
