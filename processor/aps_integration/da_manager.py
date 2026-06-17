import os
import time
import uuid
import requests
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aps_integration.aps_auth import get_aps_token
from aps_integration.oss_manager import (
    APS_BUCKET_NAME,
    create_bucket,
    generate_signed_url,
    upload_file_to_bucket,
)
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
APP_NICKNAME = CLIENT_ID # Usamos tu Client ID como nickname por simplicidad

BASE_URL = "https://developer.api.autodesk.com/da/us-east/v3"
# Motor de AutoCAD a usar en la nube
ENGINE_ID = "Autodesk.AutoCAD+24_3" 

APPBUNDLE_NAME = "DuplaExtractor"
ACTIVITY_NAME = "DuplaExtractActivity"
ZIP_PATH = os.path.join(os.path.dirname(__file__), "DuplaExtractor.zip")

def _get_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def setup_appbundle(token):
    """
    Registra el Plugin (AppBundle) en Design Automation y sube el archivo .zip.
    Esto solo se hace una vez (o cada vez que actualicemos el plugin).
    """
    print("1. Registrando AppBundle en Autodesk...")
    url = f"{BASE_URL}/appbundles"
    
    payload = {
        "id": APPBUNDLE_NAME,
        "engine": ENGINE_ID,
        "description": "Extractor de metricas de bloques y polilineas para Dupla"
    }
    
    # 1.1 Intentar crear o actualizar el registro del AppBundle
    response = requests.post(url, json=payload, headers=_get_headers(token))
    
    if response.status_code == 409:
        print("   -> El AppBundle ya estaba registrado. Creando nueva versión...")
        version_url = f"{BASE_URL}/appbundles/{APPBUNDLE_NAME}/versions"
        response = requests.post(version_url, json={"engine": ENGINE_ID}, headers=_get_headers(token))
    
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print("Error response text:", response.text)
        raise
    data = response.json()
    
    # Autodesk nos da una URL temporal para que le subamos nuestro .zip
    upload_params = data.get("uploadParameters")
    upload_url = upload_params.get("endpointURL")
    form_data = upload_params.get("formData")
    
    print("2. Subiendo el archivo DuplaExtractor.zip a la nube de Autodesk...")
    with open(ZIP_PATH, 'rb') as f:
        # formData viene como un diccionario, requerimos subirlo como multipart/form-data
        files = {'file': f}
        upload_res = requests.post(upload_url, data=form_data, files=files)
        upload_res.raise_for_status()
        
    # 1.2 Confirmar que subimos el archivo definiendo un alias ("dev")
    print("3. Publicando versión 'dev' del AppBundle...")
    version = data.get("version")
    alias_url = f"{BASE_URL}/appbundles/{APPBUNDLE_NAME}/aliases"
    
    alias_payload = {
        "version": version,
        "id": "dev"
    }
    
    alias_res = requests.post(alias_url, json=alias_payload, headers=_get_headers(token))
    if alias_res.status_code == 409: # Ya existe el alias "dev", lo actualizamos
        alias_update_url = f"{BASE_URL}/appbundles/{APPBUNDLE_NAME}/aliases/dev"
        alias_update_res = requests.patch(alias_update_url, json={"version": version}, headers=_get_headers(token))
        alias_update_res.raise_for_status()
        
    print(f"[OK] AppBundle '{APPBUNDLE_NAME}+dev' registrado y listo para usar.")


def setup_activity(token):
    """
    La Activity es la "receta". Le dice a Autodesk qué comando correr y qué entra/sale.
    """
    print("\n4. Registrando Activity (La receta de ejecución) en Autodesk...")
    url = f"{BASE_URL}/activities"
    
    # script a ejecutar dentro de AutoCAD: abrir plano, cargar dll de forma segura, llamar al comando ExtractDuplaData
    script = "EXTRACTDUPLADATA\n"
    
    payload = {
        "id": ACTIVITY_NAME,
        "commandLine": [f"$(engine.path)\\accoreconsole.exe /i \"$(args[inputFile].path)\" /al \"$(appbundles[{APPBUNDLE_NAME}].path)\" /s \"$(settings[script].path)\""],
        "parameters": {
            "inputFile": {
                "verb": "get",
                "description": "El DWG a procesar",
                "required": True,
                "localName": "$(inputFile)"
            },
            "outputJson": {
                "verb": "put",
                "description": "El JSON resultante con las mediciones",
                "required": True,
                "localName": "resultados.json" # El C# escribe en este archivo local
            }
        },
        "engine": ENGINE_ID,
        "appbundles": [f"{CLIENT_ID}.{APPBUNDLE_NAME}+dev"],
        "description": "Extrae polilineas y bloques a JSON.",
        "settings": {
            "script": {
                "value": script
            }
        }
    }

    response = requests.post(url, json=payload, headers=_get_headers(token))
    
    if response.status_code == 409:
        print("   -> La Activity ya existía. Creando nueva versión...")
        version_url = f"{BASE_URL}/activities/{ACTIVITY_NAME}/versions"
        del payload['id'] # En updates no se manda el ID
        response = requests.post(version_url, json=payload, headers=_get_headers(token))
        
    response.raise_for_status()
    version = response.json().get("version")
    
    # Crear/Actualizar el alias "dev"
    alias_url = f"{BASE_URL}/activities/{ACTIVITY_NAME}/aliases"
    alias_res = requests.post(alias_url, json={"version": version, "id": "dev"}, headers=_get_headers(token))
    if alias_res.status_code == 409:
        alias_update_url = f"{BASE_URL}/activities/{ACTIVITY_NAME}/aliases/dev"
        requests.patch(alias_update_url, json={"version": version}, headers=_get_headers(token))
        
    print(f"[OK] Activity '{ACTIVITY_NAME}+dev' publicada y lista para usar.")


def run_workitem(token, input_dwg_url, output_json_url):
    """
    El WorkItem es la orden de trabajo final. Envía un DWG a ejecutarse bajo nuestra Activity.
    """
    print("\n5. Enviando Trabajo a Autodesk (WorkItem)...")
    url = f"{BASE_URL}/workitems"
    
    payload = {
        "activityId": f"{CLIENT_ID}.{ACTIVITY_NAME}+dev",
        "arguments": {
            "inputFile": {
                "url": input_dwg_url
            },
            "outputJson": {
                "verb": "put",
                "url": output_json_url
            }
        }
    }
    
    response = requests.post(url, json=payload, headers=_get_headers(token))
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print("Error enviando WorkItem:", response.text)
        print("Payload enviado:", payload)
        raise
    
    workitem_id = response.json().get("id")
    print(f"[OK] Trabajo enviado! ID: {workitem_id}")
    return workitem_id

def check_workitem_status(token, workitem_id):
    """
    Revisa el estado del trabajo hasta que termine (success o failed).
    """
    url = f"{BASE_URL}/workitems/{workitem_id}"
    while True:
        res = requests.get(url, headers=_get_headers(token))
        status = res.json().get("status")
        print(f"   Estado actual: {status}...")
        if status in ["success", "failed", "cancelled", "failedDownload", "failedUpload", "failedInstructions"]:
            print(f"   Reporte de Autodesk: {res.json().get('reportUrl')}")
            return status
        time.sleep(3)


def ensure_da_setup(token):
    """Register/refresh the AppBundle + Activity. Run once, or after a plugin rebuild."""
    setup_appbundle(token)
    setup_activity(token)


def run_da_extraction(dwg_path, *, ensure_setup=False, bucket_name=None):
    """Full Design Automation round-trip for one DWG.

    Uploads the DWG to OSS, runs the DuplaExtractor WorkItem inside AutoCAD in
    the cloud, and returns the parsed resultados.json with true geometry
    (Polyline.Length / Area, Line.Length, vertices). Raises on non-success.
    """
    token = get_aps_token()
    bucket = bucket_name or APS_BUCKET_NAME
    if ensure_setup:
        ensure_da_setup(token)
    create_bucket(token, bucket)

    suffix = uuid.uuid4().hex[:8]
    object_name = upload_file_to_bucket(token, bucket, dwg_path, unique_suffix=f"da_{suffix}")
    if not object_name:
        raise RuntimeError(f"DA: failed to upload {dwg_path}")

    input_url = generate_signed_url(token, bucket, object_name, access="read")
    output_object = f"da_result_{suffix}.json"
    output_url = generate_signed_url(token, bucket, output_object, access="readWrite")

    workitem_id = run_workitem(token, input_url, output_url)
    status = check_workitem_status(token, workitem_id)
    if status != "success":
        raise RuntimeError(f"DA workitem {workitem_id} finished with status={status}")

    read_url = generate_signed_url(token, bucket, output_object, access="read")
    resp = requests.get(read_url)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    token = get_aps_token()
    # 1. Configurar la nube de Autodesk (solo se necesita correr una vez)
    setup_appbundle(token)
    setup_activity(token)
    print("\n¡Configuración completa! El C# ya está alojado en Autodesk.")
