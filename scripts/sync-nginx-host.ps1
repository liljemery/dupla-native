# Sincroniza deploy/nginx-host.conf → C:\nginx\conf\nginx.conf y recarga nginx.
# Ejecutar desde la raíz del repo (dupla-native):
#   powershell -ExecutionPolicy Bypass -File scripts\sync-nginx-host.ps1

$ErrorActionPreference = "Stop"

$NginxDir = "C:\nginx"
$DuplaDir = Split-Path $PSScriptRoot -Parent
$HostNginxConf = Join-Path $DuplaDir "deploy\nginx-host.conf"
$TargetNginxConf = Join-Path $NginxDir "conf\nginx.conf"
$nginxExe = Join-Path $NginxDir "nginx.exe"

if (-not (Test-Path $HostNginxConf)) { throw "No existe $HostNginxConf" }
if (-not (Test-Path $nginxExe)) { throw "No existe $nginxExe" }

Copy-Item -Path $HostNginxConf -Destination $TargetNginxConf -Force
Write-Host "Copiado -> $TargetNginxConf"

& $nginxExe -t -p $NginxDir
if ($LASTEXITCODE -ne 0) { throw "nginx -t falló" }

$nginxProc = Get-Process -Name nginx -ErrorAction SilentlyContinue
if ($nginxProc) {
    & $nginxExe -s stop -p $NginxDir
    Start-Sleep -Seconds 2
}
Start-Process -FilePath $nginxExe -WorkingDirectory $NginxDir -WindowStyle Hidden
Write-Host "nginx reiniciado"

Write-Host "`n--- client_max_body_size activo ---"
& $nginxExe -T -p $NginxDir 2>&1 | Select-String "client_max_body_size"

Write-Host "`n--- location /api/ ---"
& $nginxExe -T -p $NginxDir 2>&1 | Select-String -Pattern "location /api/|proxy_pass.*8000" -Context 0,3
