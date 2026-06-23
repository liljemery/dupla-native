import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from aps_integration.aps_auth import get_aps_token

_BACKEND_ENV = Path(__file__).resolve().parents[2] / "backend" / ".env"
if _BACKEND_ENV.is_file():
    load_dotenv(_BACKEND_ENV)
load_dotenv()

APS_BUCKET_NAME = os.getenv("APS_BUCKET_NAME", "dupla_dwg_bucket_test_01")
# Autodesk bucket names must be globally unique and lowercase.

BASE_URL = "https://developer.api.autodesk.com/oss/v2"


def _resolve_access_token(token: str | dict[str, object]) -> str:
    """Accept bare token string or APS session dict from model_derivative."""
    if isinstance(token, dict):
        return str(token.get("access_token") or token.get("token") or "")
    return str(token)


def build_object_name(file_path, object_name=None, unique_suffix=None):
    """
    Resolve the Autodesk OSS object name for an upload.

    Args:
        file_path: Local file path being uploaded.
        object_name: Optional explicit Autodesk object name override.
        unique_suffix: Optional suffix appended before the extension. This is
            useful when we want a fresh URN for retry-safe large-file runs.
    """
    resolved_name = object_name or os.path.basename(file_path)
    if not unique_suffix:
        return resolved_name

    stem, extension = os.path.splitext(resolved_name)
    normalized_suffix = str(unique_suffix).strip().replace(" ", "_")
    return f"{stem}_{normalized_suffix}{extension}"


def create_bucket(token, bucket_name):
    """
    Create an Autodesk bucket if it does not already exist.
    """
    print(f"Verificando/Creando bucket '{bucket_name}'...")
    url = f"{BASE_URL}/buckets"
    headers = {
        "Authorization": f"Bearer {_resolve_access_token(token)}",
        "Content-Type": "application/json",
    }
    payload = {
        "bucketKey": bucket_name,
        "policyKey": "transient",
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        print("[OK] Bucket creado exitosamente.")
    elif response.status_code == 409:
        print("[INFO] El bucket ya existe. Podemos usarlo.")
    else:
        print(f"[ERROR] Error al crear bucket: {response.status_code} - {response.text}")
        response.raise_for_status()


def upload_file_to_bucket(
    token,
    bucket_name,
    file_path,
    object_name=None,
    unique_suffix=None,
):
    """
    Upload a local file to Autodesk OSS using a signed write URL.
    """
    object_name = build_object_name(
        file_path,
        object_name=object_name,
        unique_suffix=unique_suffix,
    )
    print(f"Preparando subida para '{object_name}'...")

    upload_url = generate_signed_url(token, bucket_name, object_name, access="write")
    print(f"Subiendo '{object_name}' al bucket '{bucket_name}'...")
    try:
        with open(file_path, "rb") as handle:
            file_data = handle.read()

        response = requests.put(upload_url, data=file_data)
        response.raise_for_status()
        print("[OK] Archivo subido con exito.")
        return object_name
    except FileNotFoundError:
        print(f"[ERROR] El archivo no existe en la ruta: {file_path}")
        return None


def generate_signed_url(token, bucket_name, object_name, access="read"):
    """
    Generate a temporary signed Autodesk OSS URL.
    """
    print(f"Generando URL firmada para '{object_name}' ({access})...")
    url = f"{BASE_URL}/buckets/{bucket_name}/objects/{object_name}/signed"
    headers = {
        "Authorization": f"Bearer {_resolve_access_token(token)}",
        "Content-Type": "application/json",
    }
    payload = {
        "minutesExpiration": 60,
    }
    if access == "write":
        payload["singleUse"] = True
    elif access == "readWrite":
        payload["singleUse"] = False

    response = requests.post(f"{url}?access={access}", json=payload, headers=headers)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        print("Error en Signed URL:", response.text)
        raise

    signed_url = response.json().get("signedUrl")
    print("[OK] URL firmada generada con exito.")
    return signed_url


if __name__ == "__main__":
    token = get_aps_token()
    create_bucket(token, APS_BUCKET_NAME)

    test_file = r"C:\Users\chris\Downloads\8- ACAD-PLANOS GIUALCA I - RV7 - EXP.039-025.dwg SOLO IMPRESION.dwg"
    object_name = os.path.basename(test_file)
    if os.path.exists(test_file):
        upload_file_to_bucket(token, APS_BUCKET_NAME, test_file)
        url = generate_signed_url(token, APS_BUCKET_NAME, object_name)
        print(f"URL de acceso temporal: {url}")
