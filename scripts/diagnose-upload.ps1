# Diagnostico de subida: donde falla el 413 (nginx host vs backend).
#   powershell -ExecutionPolicy Bypass -File scripts\diagnose-upload.ps1

$ErrorActionPreference = "Continue"

$NginxDir = "C:\nginx"
$nginxExe = Join-Path $NginxDir "nginx.exe"

Write-Host "=== nginx en disco ==="
foreach ($path in @("$NginxDir\conf\nginx.conf", "$NginxDir\nginx.conf")) {
    if (Test-Path $path) {
        Write-Host "-- $path"
        Get-Content $path | Select-String "client_max_body_size|location /api/|proxy_pass"
    } else {
        Write-Host "-- $path (no existe)"
    }
}

Write-Host "`n=== nginx activo (-T) ==="
if (Test-Path $nginxExe) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    (& $nginxExe -T -p $NginxDir -c conf\nginx.conf 2>&1) | Select-String "client_max_body_size|location /api/|proxy_pass.*8000"
    $ErrorActionPreference = $prev
} else {
    Write-Host "No hay $nginxExe"
}

Write-Host "`n=== procesos nginx ==="
Get-Process -Name nginx -ErrorAction SilentlyContinue | Format-Table Id, Path -AutoSize

Write-Host "`n=== listeners :80 ==="
netstat -ano | Select-String "LISTENING" | Select-String ":80 "

Write-Host "`n=== POST pequeno via :80 /api/ (sin auth, esperado 401/403/422, NO 413) ==="
$tmp = New-TemporaryFile
Set-Content -Path $tmp -Value "probe" -NoNewline
try {
    curl.exe -sS -o NUL -w "HTTP %{http_code}`n" `
        -X POST "http://127.0.0.1/api/projects/00000000-0000-4000-8000-000000000001/files" `
        -F "file=@$tmp" `
        -F "wizard=true"
} finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}

Write-Host "`n=== POST pequeno directo backend :8000 (esperado 401/403/422, NO 413) ==="
$tmp2 = New-TemporaryFile
Set-Content -Path $tmp2 -Value "probe" -NoNewline
try {
    curl.exe -sS -o NUL -w "HTTP %{http_code}`n" `
        -X POST "http://127.0.0.1:8000/api/projects/00000000-0000-4000-8000-000000000001/files" `
        -F "file=@$tmp2" `
        -F "wizard=true"
} finally {
    Remove-Item $tmp2 -Force -ErrorAction SilentlyContinue
}

Write-Host "`nSi :80 devuelve 413 y :8000 no, el nginx host sigue mal."
Write-Host "Si ambos 413, revisa backend/docker."
Write-Host "El curl copiado de Chrome NO incluye el DWG; prueba en el navegador o con -F file=@ruta\real.dwg"
