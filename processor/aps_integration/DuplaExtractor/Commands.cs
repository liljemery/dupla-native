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
        // Layers whose name contains any of these tokens are legend / title-block
        // / annotation. Their geometry is *notation*, not measurable construction
        // — so a segment drawn inside the legend is never taken as a real measure.
        private static readonly string[] ExcludedLayerTokens = new[]
        {
            "leyenda", "cajetin", "cajetín", "simbolog", "titulo", "título",
            "rotulo", "rótulo", "sello", "membrete", "nota", "notas",
            "cota", "dim", "texto", "anota"
        };

        private static bool IsExcludedLayer(string layer)
        {
            if (string.IsNullOrEmpty(layer)) return false;
            string lo = layer.ToLowerInvariant();
            foreach (var token in ExcludedLayerTokens)
                if (lo.Contains(token)) return true;
            return false;
        }

        private static double SafeArcLength(Arc arc)
        {
            try { return arc.GetDistanceAtParameter(arc.EndParam); }
            catch { return arc.Radius * Math.Abs(arc.TotalAngle); }
        }

        [CommandMethod("ExtractDuplaData")]
        public void ExtractDuplaData()
        {
            var db = HostApplicationServices.WorkingDatabase;
            var results = new Dictionary<string, object>();

            var blocks = new List<object>();
            var polylines = new List<object>();
            var lines = new List<object>();
            var arcs = new List<object>();
            var circles = new List<object>();
            var texts = new List<object>();

            using (var tr = db.TransactionManager.StartTransaction())
            {
                var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                var btr = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);

                foreach (ObjectId objId in btr)
                {
                    var ent = tr.GetObject(objId, OpenMode.ForRead) as Entity;
                    if (ent == null) continue;
                    if (IsExcludedLayer(ent.Layer)) continue;

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
                        // Vertices let any single segment be measured downstream.
                        var verts = new List<object>();
                        for (int i = 0; i < pline.NumberOfVertices; i++)
                        {
                            var p = pline.GetPoint2dAt(i);
                            verts.Add(new { X = p.X, Y = p.Y });
                        }
                        polylines.Add(new {
                            Handle = pline.Handle.ToString(),
                            Layer = pline.Layer,
                            Area = pline.Area,
                            Length = pline.Length,
                            Closed = pline.Closed,
                            Vertices = verts
                        });
                    }
                    else if (ent is Line ln)
                    {
                        // Plain LINE: Model Derivative gives it no Length; here it is exact.
                        lines.Add(new {
                            Handle = ln.Handle.ToString(),
                            Layer = ln.Layer,
                            Length = ln.Length,
                            Start = new { X = ln.StartPoint.X, Y = ln.StartPoint.Y },
                            End = new { X = ln.EndPoint.X, Y = ln.EndPoint.Y }
                        });
                    }
                    else if (ent is Arc arc)
                    {
                        arcs.Add(new {
                            Handle = arc.Handle.ToString(),
                            Layer = arc.Layer,
                            Length = SafeArcLength(arc),
                            Radius = arc.Radius
                        });
                    }
                    else if (ent is Circle circ)
                    {
                        circles.Add(new {
                            Handle = circ.Handle.ToString(),
                            Layer = circ.Layer,
                            Radius = circ.Radius
                        });
                    }
                    else if (ent is DBText dtext)
                    {
                        texts.Add(new {
                            Handle = dtext.Handle.ToString(),
                            Layer = dtext.Layer,
                            Content = dtext.TextString
                        });
                    }
                    else if (ent is MText mtext)
                    {
                        texts.Add(new {
                            Handle = mtext.Handle.ToString(),
                            Layer = mtext.Layer,
                            Content = mtext.Contents
                        });
                    }
                }

                results["Blocks"] = blocks;
                results["Polylines"] = polylines;
                results["Lines"] = lines;
                results["Arcs"] = arcs;
                results["Circles"] = circles;
                results["Texts"] = texts;
                tr.Commit();
            }

            // Design Automation siempre devuelve los resultados en el directorio actual (working directory)
            string jsonString = JsonSerializer.Serialize(results, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText("resultados.json", jsonString);
        }
    }
}
