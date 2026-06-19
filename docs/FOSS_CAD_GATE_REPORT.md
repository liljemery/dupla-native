# FOSS CAD Gate Report

Decision record for replacing APS with LibreDWG + ezdxf (strict FOSS).

## Toolchain

| Step | Tool | Role |
|------|------|------|
| DWG binary → DXF | `dwg2dxf` (LibreDWG) | Required for binary `.dwg` |
| Geometry + layers | `ezdxf` via `dxf_geometry.py` | Budget `cad_facts` + clash `Element25D` |
| PDF sheets | PyMuPDF | Companion / fallback (unchanged) |

Install: `brew install libredwg` (macOS) or `apt install libredwg-bin` (Debian). Override binary with `LIBREDWG_DWG2DXF`.

## Go / no-go criteria (Fase 0)

| Check | Pass | Fail action |
|-------|------|-------------|
| `dwg2dxf` on sample DWG | DXF file created | Reject binary DWG at upload; ask for DXF export |
| ezdxf opens converted DXF | `extract_dxf_geometry` succeeds | Same as above |
| Physical entities with bounds | ≥80% of physical records have non-degenerate bounds | Document in upload UX; allow DXF passthrough |
| `cad_facts` layers | ≥1 layer with `object_count > 0` | Fall back to PDF companion in coordination |

Run spike:

```bash
python scripts/foss_cad_gate_spike.py path/to/planos/ --output /tmp/foss_gate.json
```

## Policy (production)

1. **DXF** — always accepted (native FOSS path).
2. **Binary DWG** — convert with LibreDWG on upload/worker; on failure return clear error: *Sube DXF exportado desde AutoCAD/BricsCAD*.
3. **APS** — removed from budget + coordination critical path; credentials optional for legacy viewer only.

## Parity vs APS (Fase 7)

Compare on SERENA 18 / NASAS 09:

- Budget: layer counts, `geometry_hints` length, partida totals (tolerance documented in benchmark run).
- Clashes: incident count order of magnitude, false positive/negative notes.
- Runtime: local extraction typically faster (no cloud translate/poll).

## Status

| File type | Decision |
|-----------|----------|
| `.dxf` | **GO** — primary interchange format |
| `.dwg` (binary) | **GO** when `dwg2dxf` installed; **NO-GO** otherwise (upload gate) |
| APS Model Derivative | **DEPRECATED** — replaced by `local_ezdxf` extractor |
