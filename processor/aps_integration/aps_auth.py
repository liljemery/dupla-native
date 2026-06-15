import os
import requests
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
AUTH_URL = "https://developer.api.autodesk.com/authentication/v2/token"

def get_aps_token():
    """
    Obtiene un token de acceso (2-Legged OAuth) de Autodesk Platform Services.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("Faltan configurar CLIENT_ID o CLIENT_SECRET en el archivo .env")

    # Los scopes definen los permisos. Para Design Automation y OSS necesitamos estos:
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials',
        'scope': 'data:read data:write data:create bucket:create bucket:read code:all viewables:read'
    }

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    print("Obteniendo token de autenticación de Autodesk APS...")
    response = requests.post(AUTH_URL, data=payload, headers=headers)
    
    if response.status_code == 200:
        access_token = response.json().get("access_token")
        print("[OK] Token obtenido con éxito!")
        return access_token
    else:
        print(f"[ERROR] Error al obtener token: {response.status_code} - {response.text}")
        response.raise_for_status()

if __name__ == "__main__":
    # Prueba rápida de autenticación
    token = get_aps_token()
    print(f"Token (primeros 20 caracteres): {token[:20]}...")
