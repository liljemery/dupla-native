#!/usr/bin/env python3
"""Pipeline de prueba: escanea DWGs locales, sube a APS y solicita traducción SVF2."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

MOTOR_ROOT = Path(__file__).resolve().parents[2]
MONOREPO_ROOT = MOTOR_ROOT.parent
if str(MOTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(MOTOR_ROOT))

load_dotenv(MONOREPO_ROOT / "backend" / ".env")
load_dotenv(MOTOR_ROOT / ".env")

from aps_integration.aps_auth import get_aps_token
from aps_integration.model_derivative import (
    get_manifest,
    inspect_manifest_derivatives,
    translate_to_svf2,
    urn_from_object_id,
)
from aps_integration.oss_manager import APS_BUCKET_NAME, create_bucket, upload_file_to_bucket

DEFAULT_RUTA_RAIZ = "/Users/samuelfernandez/Downloads/SERENA 18"
POLL_INTERVAL_SECONDS = 15


def escanear_dwgs_serena(ruta_raiz: str) -> list[str]:
    print(f"[*] Escaneando directorio: {ruta_raiz}")
    dwgs_a_procesar: list[str] = []

    if not os.path.exists(ruta_raiz):
        print(f"[-] Error: no se encontró la carpeta '{ruta_raiz}'.")
        return dwgs_a_procesar

    for raiz, _dirs, archivos in os.walk(ruta_raiz):
        if "ESTRUCTURAL" in raiz and "2022" in raiz:
            continue

        for archivo in archivos:
            if archivo.lower().endswith(".dwg"):
                dwgs_a_procesar.append(os.path.join(raiz, archivo))

    return dwgs_a_procesar


def verificar_estado_lote(token: str, diccionario_urns: dict[str, str]) -> tuple[int, int]:
    print("\n[*] Monitoreando conversiones en la nube de Autodesk...")
    pendientes = list(diccionario_urns.keys())
    completados = 0
    fallidos = 0

    while pendientes:
        for urn in pendientes[:]:
            archivo = diccionario_urns[urn]
            try:
                manifest = get_manifest(token, urn)
                info = inspect_manifest_derivatives(manifest)
                status = str(info.get("manifest_status", ""))
                progress = str(info.get("manifest_progress", "0%"))
                print(f"    - {os.path.basename(archivo)}: {status} ({progress})")

                if status == "success":
                    completados += 1
                    pendientes.remove(urn)
                elif status in {"failed", "timeout"}:
                    fallidos += 1
                    print(f"      [-] Error al procesar {os.path.basename(archivo)}.")
                    pendientes.remove(urn)
            except Exception as exc:
                print(f"      [!] Error consultando {os.path.basename(archivo)}: {exc}")

        if pendientes:
            print(f"    ... {len(pendientes)} pendientes; esperando {POLL_INTERVAL_SECONDS}s ...")
            time.sleep(POLL_INTERVAL_SECONDS)

    return completados, fallidos


def main() -> int:
    parser = argparse.ArgumentParser(description="Sube DWGs de SERENA 18 a APS y lanza traducción SVF2.")
    parser.add_argument("--ruta-raiz", default=DEFAULT_RUTA_RAIZ, help="Carpeta raíz con los DWG.")
    parser.add_argument("--max-files", type=int, default=0, help="Límite de archivos (0 = todos).")
    args = parser.parse_args()

    bucket_name = os.getenv("APS_BUCKET_NAME", APS_BUCKET_NAME)
    if not bucket_name:
        print("[-] APS_BUCKET_NAME no configurado en backend/.env")
        return 1

    print("=" * 60)
    print(" INICIANDO PIPELINE DE EXTRACCIÓN DWG - SERENA 18")
    print("=" * 60)
    print(f"[*] Bucket APS: {bucket_name}")

    archivos_dwg = escanear_dwgs_serena(args.ruta_raiz)
    if args.max_files > 0:
        archivos_dwg = archivos_dwg[: args.max_files]

    if not archivos_dwg:
        print("[-] No se encontraron archivos DWG para procesar.")
        return 1

    print(f"[+] Se encontraron {len(archivos_dwg)} archivos DWG válidos.\n")

    token = get_aps_token()
    create_bucket(token, bucket_name)

    diccionario_urns: dict[str, str] = {}
    subidas_ok = 0
    subidas_error = 0

    print("\n[*] Iniciando subida de archivos...")
    for ruta in archivos_dwg:
        nombre = os.path.basename(ruta)
        try:
            object_name = upload_file_to_bucket(token, bucket_name, ruta)
            if not object_name:
                subidas_error += 1
                continue

            urn = urn_from_object_id(bucket_name, object_name)
            translate_to_svf2(token, urn, views=("2d",))
            diccionario_urns[urn] = ruta
            subidas_ok += 1
            print(f"      [+] Encolado: {nombre}")
        except Exception as exc:
            subidas_error += 1
            print(f"      [-] Error con {nombre}: {exc}")

    print(f"\n[*] Subidas OK: {subidas_ok} | errores: {subidas_error}")

    completados = 0
    fallidos = 0
    if diccionario_urns:
        completados, fallidos = verificar_estado_lote(token, diccionario_urns)

    print("\n" + "=" * 60)
    if subidas_ok == 0:
        print(" PIPELINE TERMINADO SIN SUBIDAS EXITOSAS")
        print("=" * 60)
        return 1

    print(" PIPELINE FINALIZADO")
    print(f" Subidas: {subidas_ok} | traducciones OK: {completados} | fallidas: {fallidos}")
    print("=" * 60)
    return 0 if fallidos == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
