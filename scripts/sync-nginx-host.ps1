# Sincroniza deploy/nginx-host.conf al nginx de Windows y reinicia.
#   cd C:\Users\sroa\Documents\dupla-native
#   powershell -ExecutionPolicy Bypass -File scripts\sync-nginx-host.ps1

$ErrorActionPreference = "Stop"

$NginxDir = "C:\nginx"
$DuplaDir = Split-Path $PSScriptRoot -Parent
$Source = Join-Path $DuplaDir "deploy\nginx-host.conf"
$nginxExe = Join-Path $NginxDir "nginx.exe"
$ConfigRel = "conf\nginx.conf"

function Invoke-NginxOutput {
    param([Parameter(Mandatory = $true)][string[]]$NginxArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $lines = & $nginxExe @NginxArgs 2>&1
        return ($lines | Out-String)
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Stop-AllNginx {
    $procs = Get-Process -Name nginx -ErrorAction SilentlyContinue
    if (-not $procs) { return }
    foreach ($p in $procs) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 3
    $left = Get-Process -Name nginx -ErrorAction SilentlyContinue
    if ($left) {
        throw "Quedaron procesos nginx activos. Cierra DuplaStartup y ejecuta: taskkill /F /IM nginx.exe"
    }
}

if (-not (Test-Path $Source)) { throw "No existe $Source. Haz git pull primero." }
if (-not (Test-Path $nginxExe)) { throw "No existe $nginxExe" }

$sourceText = Get-Content -Path $Source -Raw
if ($sourceText -notmatch "2048m") {
    throw "deploy/nginx-host.conf no tiene 2048m. Haz git pull."
}

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

Stop-AllNginx

Invoke-NginxOutput -NginxArgs @("-t", "-p", $NginxDir, "-c", $ConfigRel) | Out-Null
if ($LASTEXITCODE -ne 0) { throw "nginx -t fallo" }

Start-Process -FilePath $nginxExe -WorkingDirectory $NginxDir -ArgumentList @("-p", $NginxDir, "-c", $ConfigRel) -WindowStyle Hidden
Start-Sleep -Seconds 2
Write-Host "nginx iniciado (-p $NginxDir -c $ConfigRel)"

$dump = Invoke-NginxOutput -NginxArgs @("-T", "-p", $NginxDir, "-c", $ConfigRel)
if ($LASTEXITCODE -ne 0) { throw "nginx -T fallo" }

Write-Host "`n--- client_max_body_size activo ---"
($dump -split "`n") | Select-String "client_max_body_size"

if ($dump -notmatch "2048m") {
    throw "nginx activo NO tiene 2048m."
}
if ($dump -notmatch "location /api/") {
    throw "nginx activo NO tiene location /api/."
}
if ($dump -match "client_max_body_size 0") {
    throw "nginx activo aun tiene client_max_body_size 0."
}

Write-Host "`n--- puerto 80 ---"
netstat -ano | Select-String ":80 " | Select-Object -First 5

Write-Host "`nOK. Prueba subida: powershell -File scripts\diagnose-upload.ps1"
Write-Host "Rebuild frontend: docker compose up -d --build"
