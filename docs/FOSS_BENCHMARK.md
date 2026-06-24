# FOSS CAD benchmark (Fase 7)

Run end-to-end without `CLIENT_ID` / `CLIENT_SECRET`.

## Checklist

```bash
# Motor
pytest motor/tests/test_dxf_geometry_extraction.py motor/tests/test_local_cad_to_cad_facts.py -q

# Processor (motor on PYTHONPATH)
PYTHONPATH=motor:processor pytest processor/tests/test_local_cad_gate.py processor/tests/test_auto_continue_budget.py -q

# Backend
pytest backend/tests/test_motor_file_discipline.py backend/tests/test_ga_fo_manifest_summary.py -q
```

## SERENA 18 E2E

1. Start stack without APS env vars.
2. Submit budget job with DWG/DXF set → verify `manifest.extractor == local_ezdxf`.
3. Submit clash job → profile `fast_compare_local`, no `--dwg-via-aps`.
4. Compare vs last APS run: partida counts, clash incident magnitude, wall-clock time.

## Expected deltas

| Metric | APS baseline | FOSS local | Notes |
|--------|--------------|------------|-------|
| Layer coverage | MD properties | ezdxf layers | May miss proxy-only entities |
| Geometry hints | properties + optional DA | bbox/length from DXF | Scale calibrator still applies |
| Clash elements | APS viewer / accore | ezdxf footprints | 2.5D unchanged |
| Cloud deps | CLIENT_ID required | None on critical path | Viewer APS deprecated |

Record actual numbers from your SERENA run in this file when available.
