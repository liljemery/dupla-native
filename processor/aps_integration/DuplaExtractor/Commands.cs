using System;
using System.IO;
using System.Text;
using System.Globalization;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.ApplicationServices.Core;
using Autodesk.AutoCAD.DatabaseServices;

// Registers the command class. ExtensionApplication(null) = no initializer needed.
[assembly: CommandClass(typeof(DuplaExtractor.Commands))]
[assembly: ExtensionApplication(null)]

namespace DuplaExtractor
{
    public class Commands
    {
        // JSON is built by hand (StringBuilder) ON PURPOSE: System.Text.Json drags
        // a tree of 8 facade DLLs (System.Memory/Buffers/Unsafe/...) that fail to
        // bind inside the AutoCAD core console on .NET 4.8, which makes the whole
        // assembly fail to load -> "Unknown command EXTRACTDUPLADATA". With zero
        // external deps the bundle is just DuplaExtractor.dll and loads cleanly.

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

        private static string N(double d)
        {
            if (double.IsNaN(d) || double.IsInfinity(d)) return "0";
            return d.ToString("R", CultureInfo.InvariantCulture);
        }

        private static void Str(StringBuilder sb, string s)
        {
            sb.Append('"');
            if (s != null)
            {
                foreach (char c in s)
                {
                    if (c == '"') sb.Append("\\\"");
                    else if (c == '\\') sb.Append("\\\\");
                    else if (c == '\n') sb.Append("\\n");
                    else if (c == '\r') sb.Append("\\r");
                    else if (c == '\t') sb.Append("\\t");
                    else if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                    else sb.Append(c);
                }
            }
            sb.Append('"');
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
            var blocks = new StringBuilder();
            var polylines = new StringBuilder();
            var lines = new StringBuilder();
            var arcs = new StringBuilder();
            var circles = new StringBuilder();
            var texts = new StringBuilder();

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
                        var btrRef = (BlockTableRecord)tr.GetObject(br.DynamicBlockTableRecord, OpenMode.ForRead);
                        if (blocks.Length > 0) blocks.Append(',');
                        blocks.Append("{\"Handle\":"); Str(blocks, br.Handle.ToString());
                        blocks.Append(",\"Layer\":"); Str(blocks, br.Layer);
                        blocks.Append(",\"Name\":"); Str(blocks, btrRef.Name);
                        blocks.Append(",\"X\":").Append(N(br.Position.X));
                        blocks.Append(",\"Y\":").Append(N(br.Position.Y)).Append('}');
                    }
                    else if (ent is Polyline pl)
                    {
                        if (polylines.Length > 0) polylines.Append(',');
                        polylines.Append("{\"Handle\":"); Str(polylines, pl.Handle.ToString());
                        polylines.Append(",\"Layer\":"); Str(polylines, pl.Layer);
                        polylines.Append(",\"Area\":").Append(N(pl.Area));
                        polylines.Append(",\"Length\":").Append(N(pl.Length));
                        polylines.Append(",\"Closed\":").Append(pl.Closed ? "true" : "false");
                        polylines.Append(",\"Vertices\":[");
                        for (int i = 0; i < pl.NumberOfVertices; i++)
                        {
                            var p = pl.GetPoint2dAt(i);
                            if (i > 0) polylines.Append(',');
                            polylines.Append("{\"X\":").Append(N(p.X)).Append(",\"Y\":").Append(N(p.Y)).Append('}');
                        }
                        polylines.Append("]}");
                    }
                    else if (ent is Line ln)
                    {
                        if (lines.Length > 0) lines.Append(',');
                        lines.Append("{\"Handle\":"); Str(lines, ln.Handle.ToString());
                        lines.Append(",\"Layer\":"); Str(lines, ln.Layer);
                        lines.Append(",\"Length\":").Append(N(ln.Length));
                        lines.Append(",\"StartX\":").Append(N(ln.StartPoint.X));
                        lines.Append(",\"StartY\":").Append(N(ln.StartPoint.Y));
                        lines.Append(",\"EndX\":").Append(N(ln.EndPoint.X));
                        lines.Append(",\"EndY\":").Append(N(ln.EndPoint.Y)).Append('}');
                    }
                    else if (ent is Arc arc)
                    {
                        if (arcs.Length > 0) arcs.Append(',');
                        arcs.Append("{\"Handle\":"); Str(arcs, arc.Handle.ToString());
                        arcs.Append(",\"Layer\":"); Str(arcs, arc.Layer);
                        arcs.Append(",\"Length\":").Append(N(SafeArcLength(arc)));
                        arcs.Append(",\"Radius\":").Append(N(arc.Radius)).Append('}');
                    }
                    else if (ent is Circle circ)
                    {
                        if (circles.Length > 0) circles.Append(',');
                        circles.Append("{\"Handle\":"); Str(circles, circ.Handle.ToString());
                        circles.Append(",\"Layer\":"); Str(circles, circ.Layer);
                        circles.Append(",\"Radius\":").Append(N(circ.Radius)).Append('}');
                    }
                    else if (ent is DBText dt)
                    {
                        if (texts.Length > 0) texts.Append(',');
                        texts.Append("{\"Handle\":"); Str(texts, dt.Handle.ToString());
                        texts.Append(",\"Layer\":"); Str(texts, dt.Layer);
                        texts.Append(",\"Content\":"); Str(texts, dt.TextString); texts.Append('}');
                    }
                    else if (ent is MText mt)
                    {
                        if (texts.Length > 0) texts.Append(',');
                        texts.Append("{\"Handle\":"); Str(texts, mt.Handle.ToString());
                        texts.Append(",\"Layer\":"); Str(texts, mt.Layer);
                        texts.Append(",\"Content\":"); Str(texts, mt.Contents); texts.Append('}');
                    }
                }
                tr.Commit();
            }

            var json = new StringBuilder();
            json.Append("{\"Blocks\":[").Append(blocks).Append("],");
            json.Append("\"Polylines\":[").Append(polylines).Append("],");
            json.Append("\"Lines\":[").Append(lines).Append("],");
            json.Append("\"Arcs\":[").Append(arcs).Append("],");
            json.Append("\"Circles\":[").Append(circles).Append("],");
            json.Append("\"Texts\":[").Append(texts).Append("]}");

            // Design Automation returns whatever the WorkItem wrote to the working dir.
            File.WriteAllText("resultados.json", json.ToString());
        }
    }
}
