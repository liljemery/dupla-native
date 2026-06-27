# Sincroniza deploy/nginx-host.conf al nginx de Windows y reinicia.
#   cd C:\Users\sroa\Documents\dupla-native
#   powershell -ExecutionPolicy Bypass -File scripts\sync-nginx-host.ps1
#
# Luego rebuild frontend:
#   docker compose up -d --build

$ErrorActionPreference = "Stop"

$NginxDir = "C:\nginx"
$DuplaDir = Split-Path $PSScriptRoot -Parent
$Source = Join-Path $DuplaDir "deploy\nginx-host.conf"
$nginxExe = Join-Path $NginxDir "nginx.exe"
$ConfigRel = "conf\nginx.conf"

function Invoke-NginxOutput {
    param([Parameter(Mandatory = $true)][string[]]$NginxArgs)
    # nginx escribe "syntax is ok" en stderr; no tratarlo como error de PowerShell.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $lines = & $nginxExe @NginxArgs 2>&1
        return ($lines | Out-String)
    } finally {
        $ErrorActionPreference = $prev
    }
}

if (-not (Test-Path $Source)) { throw "No existe $Source. Haz git pull primero." }
if (-not (Test-Path $nginxExe)) { throw "No existe $nginxExe" }

$targets = @(
    (Join-Path $NginxDir $ConfigRel),
    (Join-Path $NginxDir "nginx.conf")
)
foreach ($target in $targets) {
    $dir = Split-Path $target -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Copy-Item -Path $Source -Destination $target -Force
    Write-Host "Copiado -> $target"
}

Invoke-NginxOutput -NginxArgs @("-t", "-p", $NginxDir, "-c", $ConfigRel) | Out-Null
if ($LASTEXITCODE -ne 0) { throw "nginx -t fallo" }

$nginxProc = Get-Process -Name nginx -ErrorAction SilentlyContinue
if ($nginxProc) {
    Invoke-NginxOutput -NginxArgs @("-s", "stop", "-p", $NginxDir) | Out-Null
    Start-Sleep -Seconds 2
}
Start-Process -FilePath $nginxExe -WorkingDirectory $NginxDir -ArgumentList @("-p", $NginxDir, "-c", $ConfigRel) -WindowStyle Hidden
Start-Sleep -Seconds 1
Write-Host "nginx reiniciado (-p $NginxDir -c $ConfigRel)"

$dump = Invoke-NginxOutput -NginxArgs @("-T", "-p", $NginxDir, "-c", $ConfigRel)
if ($LASTEXITCODE -ne 0) { throw "nginx -T fallo" }

Write-Host "`n--- client_max_body_size activo ---"
($dump -split "`n") | Select-String "client_max_body_size"

if ($dump -notmatch "2048m") {
    throw "nginx sigue sin 2048m. Comprueba DuplaStartup u otro nginx en PATH."
}
if ($dump -notmatch "location /api/") {
    throw "nginx no tiene location /api/. /api sigue yendo al contenedor :5173."
}

Write-Host "`nOK. Rebuild frontend: docker compose up -d --build"
