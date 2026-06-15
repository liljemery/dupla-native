import os
import subprocess
import shutil
import zipfile

PROJECT_DIR = os.path.join(os.path.dirname(__file__), "DuplaExtractor")
BUNDLE_DIR = os.path.join(os.path.dirname(__file__), "DuplaExtractor.bundle")
OUTPUT_ZIP = os.path.join(os.path.dirname(__file__), "DuplaExtractor.zip")

CS_CODE = """using System;
using System.IO;
using System.Text.Json;
using System.Collections.Generic;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.ApplicationServices.Core;
using Autodesk.AutoCAD.DatabaseServices;

// This assembly attribute explicitly registers our CommandClass
[assembly: CommandClass(typeof(DuplaExtractor.Commands))]
[assembly: ExtensionApplication(null)]

namespace DuplaExtractor
{

    public class Commands
    {
        [CommandMethod("ExtractDuplaData")]
        public void ExtractDuplaData()
        {
            var db = HostApplicationServices.WorkingDatabase;
            var results = new Dictionary<string, object>();
            
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                var btr = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);
                
                var blocks = new List<object>();
                var polylines = new List<object>();

                foreach (ObjectId objId in btr)
                {
                    var ent = tr.GetObject(objId, OpenMode.ForRead) as Entity;
                    if (ent == null) continue;

                    if (ent is BlockReference br)
                    {
                        var props = new Dictionary<string, string>();
                        // Extraer atributos
                        foreach (ObjectId attId in br.AttributeCollection)
                        {
                            var att = tr.GetObject(attId, OpenMode.ForRead) as AttributeReference;
                            if (att != null)
                            {
                                props[att.Tag] = att.TextString;
                            }
                        }
                        
                        // Propiedades dinamicas
                        if (br.IsDynamicBlock)
                        {
                            foreach (DynamicBlockReferenceProperty prop in br.DynamicBlockReferencePropertyCollection)
                            {
                                props[prop.PropertyName] = prop.Value?.ToString() ?? "";
                            }
                        }
                        
                        var btrRef = (BlockTableRecord)tr.GetObject(br.DynamicBlockTableRecord, OpenMode.ForRead);

                        blocks.Add(new {
                            Handle = br.Handle.ToString(),
                            Layer = br.Layer,
                            Name = btrRef.Name,
                            Attributes = props,
                            Position = new { X = br.Position.X, Y = br.Position.Y }
                        });
                    }
                    else if (ent is Polyline pline)
                    {
                        polylines.Add(new {
                            Handle = pline.Handle.ToString(),
                            Layer = pline.Layer,
                            Area = pline.Area,
                            Length = pline.Length,
                            Closed = pline.Closed
                        });
                    }
                }
                
                results["Blocks"] = blocks;
                results["Polylines"] = polylines;
                tr.Commit();
            }
            
            // Design Automation siempre devuelve los resultados en el directorio actual (working directory)
            string jsonString = JsonSerializer.Serialize(results, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText("resultados.json", jsonString);
        }
    }
}
"""

CSPROJ_CODE = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net48</TargetFramework>
    <UseWindowsForms>true</UseWindowsForms>
    <EnableDynamicLoading>true</EnableDynamicLoading>
    <CopyLocalLockFileAssemblies>true</CopyLocalLockFileAssemblies>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="AutoCAD.NET.Core" Version="24.3.*" ExcludeAssets="runtime" />
    <PackageReference Include="AutoCAD.NET" Version="24.3.*" ExcludeAssets="runtime" />
    <PackageReference Include="System.Text.Json" Version="8.0.0" />
  </ItemGroup>
</Project>
"""

PACKAGE_XML = """<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0" AppVersion="1.0" Author="Dupla" Name="DuplaExtractor" Description="Extrae datos de bloques y polilineas a JSON">
  <Components>
    <RuntimeRequirements OS="Win64" Platform="AutoCAD" SeriesMin="R24.0" SeriesMax="R24.3" />
    <ComponentEntry AppName="DuplaExtractor" Version="1.0" ModuleName="./Contents/DuplaExtractor.dll" AppDescription="Extractor de cantidades" LoadOnAutoCADStartup="true" />
  </Components>
</ApplicationPackage>
"""

def create_bundle():
    print("1. Creando proyecto en C#...")
    if os.path.exists(PROJECT_DIR):
        shutil.rmtree(PROJECT_DIR)
    os.makedirs(PROJECT_DIR)
    
    with open(os.path.join(PROJECT_DIR, "Commands.cs"), "w", encoding="utf-8") as f:
        f.write(CS_CODE)
        
    with open(os.path.join(PROJECT_DIR, "DuplaExtractor.csproj"), "w", encoding="utf-8") as f:
        f.write(CSPROJ_CODE)
        
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
                
    print(f"✅ ¡Plugin C# compilado y empaquetado como '{os.path.basename(OUTPUT_ZIP)}'!")

if __name__ == "__main__":
    create_bundle()
