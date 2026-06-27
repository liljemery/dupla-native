# Dupla — arranque local desde cero sin Docker (Windows).
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\setup-from-scratch.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup-from-scratch.ps1 -Action Stop
#   powershell -ExecutionPolicy Bypass -File scripts\setup-from-scratch.ps1 -Action Status
#   powershell -ExecutionPolicy Bypass -File scripts\setup-from-scratch.ps1 -SkipBootstrap

param(
  [ValidateSet("Init", "Stop", "Status", "Help")]
  [string] $Action = "Init",
  [switch] $SkipBootstrap
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
$BACKEND = Join-Path $ROOT "backend"
$PROC = Join-Path $ROOT "processor"
$COORD = Join-Path $ROOT "coordination-service"
$FRONT = Join-Path $ROOT "frontend"
$VAR = Join-Path $ROOT "var"
$PID_DIR = Join-Path $VAR "pids"
$LOGS = Join-Path $VAR "logs"

function Show-Help {
  @"
Dupla — setup local sin Docker (Windows)

Uso:
  powershell -ExecutionPolicy Bypass -File scripts\setup-from-scratch.ps1
  powershell -ExecutionPolicy Bypass -File scripts\setup-from-scratch.ps1 -Action Stop|Status|Help

Opciones:
  -SkipBootstrap   Omite migraciones/seed (DB ya inicializada)

Requisitos:
  PostgreSQL 16+ en 127.0.0.1:5432 (usuario/db dupla/dupla)
  Redis 7+ en 127.0.0.1:6379
  Python 3.12+ (py launcher o python en PATH)
  pnpm (npm install -g pnpm)

Instalar infra (ejemplo):
  winget install PostgreSQL.PostgreSQL.16
  winget install Redis.Redis
  Tras Postgres, crear usuario dupla y base dupla (ver README).

URLs: http://localhost:5173 | http://localhost:8000/docs
Demo: master@dupla.demo / master123
"@
}

function Test-PortOpen([string] $HostName, [int] $Port) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $iar = $c.BeginConnect($HostName, $Port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(500, $false)
    if ($ok -and $c.Connected) { $c.Close(); return $true }
    $c.Close()
  } catch {}
  return $false
}

function Wait-Port([string] $HostName, [int] $Port, [string] $Label, [int] $Max = 90) {
  for ($i = 1; $i -le $Max; $i++) {
    if (Test-PortOpen $HostName $Port) {
      Write-Host "OK — $Label en ${HostName}:$Port"
      return
    }
    Write-Host "Esperando $Label (${HostName}:$Port)… $i/$Max"
    Start-Sleep -Seconds 1
  }
  throw "$Label no responde en ${HostName}:$Port. Inicia PostgreSQL y Redis."
}

function Resolve-PythonExe([string] $Profile) {
  $vers = if ($Profile -eq "backend") { @("3.12", "3.13") } else { @("3.12", "3.11", "3.13") }
  foreach ($v in $vers) {
    try {
      $exe = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
      if ($exe) { return $exe.Trim() }
    } catch {}
  }
  foreach ($name in @("python3.12", "python3", "python")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
  }
  throw "Python no encontrado. Instala Python 3.12+ (python.org o winget install Python.Python.3.12)"
}

function Ensure-Venv([string] $Dir, [string] $Profile) {
  $py = Resolve-PythonExe $Profile
  $venvPy = Join-Path $Dir ".venv\Scripts\python.exe"
  if (Test-Path $venvPy) {
    $ver = & $venvPy -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    $want = (& $py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($ver -ne $want) {
      Write-Host "==> Recreando venv en $Dir"
      Remove-Item -Recurse -Force (Join-Path $Dir ".venv")
    }
  }
  if (-not (Test-Path $venvPy)) {
    Write-Host "==> Creando venv en $Dir"
    & $py -m venv (Join-Path $Dir ".venv")
  }
  Write-Host "==> pip install $Dir"
  & $venvPy -m pip install -q -r (Join-Path $Dir "requirements.txt")
}

function Ensure-PostgresDuplaDb {
  $psql = Get-Command psql -ErrorAction SilentlyContinue
  if (-not $psql) {
    Write-Host @"
AVISO: psql no está en PATH. Crea manualmente en pgAdmin o psql:
  CREATE USER dupla WITH PASSWORD 'dupla' SUPERUSER;
  CREATE DATABASE dupla OWNER dupla;
"@
    return
  }
  Write-Host "==> Usuario y base PostgreSQL dupla"
  $sql = @"
DO `$`$ BEGIN
  CREATE USER dupla WITH PASSWORD 'dupla' SUPERUSER;
EXCEPTION WHEN duplicate_object THEN
  ALTER USER dupla WITH PASSWORD 'dupla';
END `$`$;
"@
  & psql -U postgres -d postgres -v ON_ERROR_STOP=0 -c $sql 2>$null | Out-Null
  & psql -U postgres -d postgres -v ON_ERROR_STOP=0 -c "CREATE DATABASE dupla OWNER dupla;" 2>$null | Out-Null
}

function Load-BackendEnv {
  $envFile = Join-Path $BACKEND ".env"
  if (-not (Test-Path $envFile)) { return }
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
      $i = $line.IndexOf("=")
      $k = $line.Substring(0, $i).Trim()
      $v = $line.Substring($i + 1).Trim()
      Set-Item -Path "env:$k" -Value $v
    }
  }
}

function Set-DevDefaults {
  if (-not $env:DUPLA_ROOT) { $env:DUPLA_ROOT = Join-Path $ROOT "motor" }
  if (-not $env:COORDINATION_OUTPUT_ROOT) { $env:COORDINATION_OUTPUT_ROOT = Join-Path $VAR "coord_outputs" }
  if (-not $env:DUPLA_CACHE_DIR) { $env:DUPLA_CACHE_DIR = Join-Path $VAR "cache" }
  if (-not $env:DUPLA_ARTIFACT_DIR) { $env:DUPLA_ARTIFACT_DIR = Join-Path $VAR "artifacts" }
  if (-not $env:COORDINATION_CACHE_ROOT) { $env:COORDINATION_CACHE_ROOT = Join-Path $VAR "coord_outputs\cad_cache" }
  if (-not $env:COORDINATION_SMOKE_MODE) { $env:COORDINATION_SMOKE_MODE = "true" }
  if (-not $env:REDIS_URL) { $env:REDIS_URL = "redis://127.0.0.1:6379/0" }
  $env:PYTHONPATH = "$($env:DUPLA_ROOT);$COORD;$($env:PYTHONPATH)"
}

function Write-PidFile([string] $Name, [int] $ProcessId) {
  Set-Content -Path (Join-Path $PID_DIR "$Name.pid") -Value $ProcessId -NoNewline
}

function Read-PidFile([string] $Name) {
  $f = Join-Path $PID_DIR "$Name.pid"
  if (Test-Path $f) { return [int](Get-Content $f -Raw) }
  return $null
}

function Test-ProcessRunning([int] $ProcessId) {
  if (-not $ProcessId) { return $false }
  return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Stop-PidTree([int] $ProcessId) {
  if (-not (Test-ProcessRunning $ProcessId)) { return }
  Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-PidTree $_.ProcessId }
  Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Start-Detached([string] $Name, [string] $Exe, [string[]] $ArgList, [string] $WorkDir) {
  $logOut = Join-Path $LOGS "$Name.log"
  $logErr = Join-Path $LOGS "$Name.err.log"
  $p = Start-Process -FilePath $Exe -ArgumentList $ArgList -WorkingDirectory $WorkDir `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $logOut -RedirectStandardError $logErr
  Write-PidFile $Name $p.Id
  Write-Host "started $Name (pid $($p.Id))"
}

function Invoke-Setup {
  New-Item -ItemType Directory -Force -Path @(
    (Join-Path $VAR "uploads"),
    (Join-Path $VAR "cache"),
    (Join-Path $VAR "artifacts"),
    (Join-Path $VAR "coord_outputs"),
    (Join-Path $VAR "coord_outputs\cad_cache"),
    (Join-Path $VAR "processor_outputs"),
    (Join-Path $BACKEND "var\uploads"),
    $PID_DIR, $LOGS
  ) | Out-Null

  $envExample = Join-Path $BACKEND ".env.example"
  $envFile = Join-Path $BACKEND ".env"
  if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Host "Creado backend\.env"
  }

  Ensure-Venv $BACKEND "backend"
  Ensure-Venv $PROC "default"
  Ensure-Venv $COORD "default"

  if (-not (Test-Path (Join-Path $FRONT "node_modules"))) {
    Write-Host "==> pnpm install (frontend)"
    Push-Location $FRONT
    pnpm install
    Pop-Location
  }
}

function Invoke-Bootstrap {
  $bpy = Join-Path $BACKEND ".venv\Scripts\python.exe"
  Push-Location $BACKEND
  & $bpy -m app.db.migrate_bootstrap
  & $bpy -m alembic upgrade head
  & $bpy -m app.seed
  Pop-Location
  Write-Host "OK — base de datos lista"
}

function Invoke-Start {
  Load-BackendEnv
  Set-DevDefaults

  $bpy = Join-Path $BACKEND ".venv\Scripts\python.exe"
  $ppy = Join-Path $PROC ".venv\Scripts\python.exe"
  $cpy = Join-Path $COORD ".venv\Scripts\python.exe"

  if (Test-ProcessRunning (Read-PidFile "backend")) {
    Write-Host "Servicios ya en ejecución. Usa -Action Stop"
    Invoke-Status
    return
  }

  New-Item -ItemType Directory -Force -Path $LOGS | Out-Null

  Start-Detached "backend" $bpy @("-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000") $BACKEND
  Start-Detached "processor" $ppy @("-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8001") $PROC
  Start-Detached "processor-worker" $ppy @("worker.py") $PROC
  Start-Detached "coordination" $cpy @("-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8002") $COORD
  Start-Detached "coordination-worker" $cpy @("worker.py") $COORD

  $frontLog = Join-Path $LOGS "frontend.log"
  $frontErr = Join-Path $LOGS "frontend.err.log"
  $fp = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/c", "pnpm", "dev", "--host", "127.0.0.1", "--port", "5173") `
    -WorkingDirectory $FRONT -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $frontLog -RedirectStandardError $frontErr
  Write-PidFile "frontend" $fp.Id
  Write-Host "started frontend (pid $($fp.Id))"

  Start-Sleep -Seconds 2
  Invoke-Status
  Write-Host ""
  Write-Host "Logs: $LOGS"
}

function Invoke-Stop {
  foreach ($name in @("frontend", "backend", "processor", "processor-worker", "coordination", "coordination-worker")) {
    $processId = Read-PidFile $name
    if (Test-ProcessRunning $processId) {
      Write-Host "Deteniendo $name (pid $processId)"
      Stop-PidTree $processId
    }
    Remove-Item (Join-Path $PID_DIR "$name.pid") -ErrorAction SilentlyContinue
  }
  Write-Host "OK — servicios detenidos"
}

function Invoke-Status {
  foreach ($name in @("frontend", "backend", "processor", "processor-worker", "coordination", "coordination-worker")) {
    $processId = Read-PidFile $name
    if (Test-ProcessRunning $processId) { Write-Host "$name`: running (pid $processId)" }
    else { Write-Host "$name`: stopped" }
  }
  Write-Host ""
  Write-Host "URLs:"
  Write-Host "  Frontend     http://localhost:5173"
  Write-Host "  Backend      http://localhost:8000/docs"
  Write-Host "  Processor    http://localhost:8001"
  Write-Host "  Coordination http://localhost:8002/health"
}

function Invoke-Init {
  Write-Host "==> Dupla — setup desde cero (sin Docker)"
  if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    throw "pnpm no encontrado. Ejecuta: npm install -g pnpm"
  }

  Ensure-PostgresDuplaDb
  Wait-Port "127.0.0.1" 5432 "PostgreSQL"
  Wait-Port "127.0.0.1" 6379 "Redis"

  Invoke-Setup

  if (-not $SkipBootstrap) {
    Write-Host "==> Bootstrap (migraciones + seed)"
    Invoke-Bootstrap
  } else {
    Write-Host "==> Omitiendo bootstrap (-SkipBootstrap)"
  }

  Invoke-Start
}

switch ($Action) {
  "Init" { Invoke-Init }
  "Stop" { Invoke-Stop }
  "Status" { Invoke-Status }
  "Help" { Show-Help }
}
