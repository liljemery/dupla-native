# Arranque en Windows: nginx host + docker compose.
# Sincroniza deploy/nginx-host.conf → C:\nginx\conf\nginx.conf en cada arranque.
#
# Registrar una vez (PowerShell como administrador):
#   Set-ExecutionPolicy -Scope LocalMachine RemoteSigned
#   Register-ScheduledTask -TaskName "DuplaStartup" `
#     -Action (New-ScheduledTaskAction -Execute "powershell.exe" `
#       -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\Users\sroa\Documents\dupla-native\scripts\windows-compose-startup.ps1"') `
#     -Trigger (New-ScheduledTaskTrigger -AtLogon -User "sroa") `
#     -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable) `
#     -Principal (New-ScheduledTaskPrincipal -UserId "sroa" -LogonType Interactive -RunLevel Highest)

$ErrorActionPreference = "Stop"

$StartupDelaySeconds = 90
$NginxDir = "C:\nginx"
$DuplaDir = Split-Path $PSScriptRoot -Parent
$HostNginxConf = Join-Path $DuplaDir "deploy\nginx-host.conf"
$TargetNginxConf = Join-Path $NginxDir "conf\nginx.conf"
$LogFile = Join-Path $DuplaDir "var\logs\windows-startup.log"

function Write-Log([string]$Message) {
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Message
    $dir = Split-Path $LogFile -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Add-Content -Path $LogFile -Value $line
}

function Wait-DockerReady {
    param([int]$MaxSeconds = 300)
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 10
    }
    throw "Docker no respondió en ${MaxSeconds}s"
}

function Sync-HostNginx {
    if (-not (Test-Path $HostNginxConf)) { throw "No existe $HostNginxConf" }
    $confDir = Split-Path $TargetNginxConf -Parent
    if (-not (Test-Path $confDir)) { New-Item -ItemType Directory -Force -Path $confDir | Out-Null }
    Copy-Item -Path $HostNginxConf -Destination $TargetNginxConf -Force
    Write-Log "nginx conf sincronizado desde deploy/nginx-host.conf"

    $nginxExe = Join-Path $NginxDir "nginx.exe"
    & $nginxExe -t -p $NginxDir
    if ($LASTEXITCODE -ne 0) { throw "nginx -t falló" }
}

function Start-OrReloadHostNginx {
    $nginxExe = Join-Path $NginxDir "nginx.exe"
    $nginxProc = Get-Process -Name nginx -ErrorAction SilentlyContinue
    if ($nginxProc) {
        & $nginxExe -s reload -p $NginxDir
        if ($LASTEXITCODE -ne 0) { throw "nginx -s reload falló" }
        Write-Log "nginx recargado"
    } else {
        Start-Process -FilePath $nginxExe -WorkingDirectory $NginxDir -WindowStyle Hidden
        Write-Log "nginx iniciado"
    }
}

try {
    Write-Log "startup begin (espera ${StartupDelaySeconds}s para Docker)"
    Start-Sleep -Seconds $StartupDelaySeconds

    if (-not (Test-Path $NginxDir)) { throw "No existe $NginxDir" }
    Sync-HostNginx
    Start-OrReloadHostNginx

    if (-not (Test-Path $DuplaDir)) { throw "No existe $DuplaDir" }
    Wait-DockerReady
    Write-Log "docker listo"

    Set-Location $DuplaDir
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw "docker compose falló con código $LASTEXITCODE" }
    Write-Log "docker compose up ok"
}
catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    throw
}
