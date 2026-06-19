import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# Monorepo: credenciales APS viven en backend/.env (cargado también por coordination-service).
_MONOREPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ENV = _MONOREPO_ROOT / "backend" / ".env"
if _BACKEND_ENV.is_file():
    load_dotenv(_BACKEND_ENV)
load_dotenv(_MONOREPO_ROOT / ".env")
load_dotenv()

AUTH_URL = "https://developer.api.autodesk.com/authentication/v2/token"


def get_aps_token() -> str:
    """Obtiene un token de acceso (2-Legged OAuth) de Autodesk Platform Services."""
    client_id = (os.getenv("CLIENT_ID") or os.getenv("APS_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("CLIENT_SECRET") or os.getenv("APS_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise ValueError(
            "Faltan CLIENT_ID / CLIENT_SECRET en backend/.env (o variables de entorno del worker)."
        )

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": "data:read data:write data:create bucket:create bucket:read code:all viewables:read",
    }
    response = requests.post(AUTH_URL, data=payload, timeout=30)
    if response.status_code == 200:
        token = response.json().get("access_token")
        if not token:
            raise ValueError("APS no devolvió access_token")
        return token
    response.raise_for_status()
    raise RuntimeError("unreachable")

if __name__ == "__main__":
    # Prueba rápida de autenticación
    token = get_aps_token()
    print(f"Token (primeros 20 caracteres): {token[:20]}...")
