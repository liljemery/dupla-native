using System;
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
