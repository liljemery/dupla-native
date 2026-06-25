# Arranque en Windows: nginx + docker compose (dupla-native).
# Registrar una vez (PowerShell como administrador):
#   Set-ExecutionPolicy -Scope LocalMachine RemoteSigned
#   Register-ScheduledTask -TaskName "DuplaStartup" `
#     -Action (New-ScheduledTaskAction -Execute "powershell.exe" `
#       -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\sroa\Documents\dupla-native\scripts\windows-compose-startup.ps1"') `
#     -Trigger (New-ScheduledTaskTrigger -AtLogon -User "sroa" -Delay (New-TimeSpan -Seconds 90)) `
#     -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable) `
#     -Principal (New-ScheduledTaskPrincipal -UserId "sroa" -LogonType Interactive -RunLevel Highest)

$ErrorActionPreference = "Stop"

$NginxDir = "C:\nginx"
$DuplaDir = "C:\Users\sroa\Documents\dupla-native"
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

try {
    Write-Log "startup begin"

    if (-not (Test-Path $NginxDir)) { throw "No existe $NginxDir" }
    Set-Location $NginxDir
    $nginxProc = Get-Process -Name nginx -ErrorAction SilentlyContinue
    if ($nginxProc) {
        Write-Log "nginx ya en ejecución"
    } else {
        Start-Process -FilePath (Join-Path $NginxDir "nginx.exe") -WorkingDirectory $NginxDir -WindowStyle Hidden
        Write-Log "nginx iniciado"
    }

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
