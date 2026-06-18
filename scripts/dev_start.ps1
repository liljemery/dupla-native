# Windows equivalent of scripts/dev.sh `start`.
# Loads backend/.env, sets the same env defaults, and launches all 6 services
# (backend, processor API + worker, coordination API + worker, frontend) in the
# background with logs under var/logs.

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
$BACKEND  = Join-Path $ROOT "backend"
$PROC     = Join-Path $ROOT "processor"
$COORD    = Join-Path $ROOT "coordination-service"
$FRONT    = Join-Path $ROOT "frontend"
$VAR      = Join-Path $ROOT "var"
$LOGS     = Join-Path $VAR "logs"

New-Item -ItemType Directory -Force -Path $LOGS, (Join-Path $VAR "cache"), (Join-Path $VAR "artifacts"), (Join-Path $VAR "coord_outputs"), (Join-Path $VAR "uploads") | Out-Null

# --- load backend/.env ---
$envFile = Join-Path $BACKEND ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
      $i = $line.IndexOf("=")
      $k = $line.Substring(0, $i).Trim()
      $v = $line.Substring($i + 1).Trim()
      [Environment]::SetEnvironmentVariable($k, $v, "Process")
    }
  }
}

# --- dev.sh defaults ---
if (-not $env:DUPLA_ROOT)              { $env:DUPLA_ROOT = Join-Path $ROOT "motor" }
if (-not $env:COORDINATION_OUTPUT_ROOT){ $env:COORDINATION_OUTPUT_ROOT = Join-Path $VAR "coord_outputs" }
if (-not $env:DUPLA_CACHE_DIR)         { $env:DUPLA_CACHE_DIR = Join-Path $VAR "cache" }
if (-not $env:DUPLA_ARTIFACT_DIR)      { $env:DUPLA_ARTIFACT_DIR = Join-Path $VAR "artifacts" }
if (-not $env:COORDINATION_SMOKE_MODE) { $env:COORDINATION_SMOKE_MODE = "false" }
if (-not $env:REDIS_URL)               { $env:REDIS_URL = "redis://127.0.0.1:6379/0" }
$env:PYTHONPATH = "$($env:DUPLA_ROOT);$COORD;$($env:PYTHONPATH)"

function Start-Svc($name, $py, $argList, $dir) {
  Start-Process -FilePath $py -ArgumentList $argList -WorkingDirectory $dir -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LOGS "$name.log") `
    -RedirectStandardError  (Join-Path $LOGS "$name.err.log") | Out-Null
  Write-Host "started $name"
}

$bpy = Join-Path $BACKEND ".venv\Scripts\python.exe"
$ppy = Join-Path $PROC    ".venv\Scripts\python.exe"
$cpy = Join-Path $COORD   ".venv\Scripts\python.exe"

Start-Svc "backend"             $bpy @("-m","uvicorn","app.main:app","--reload","--host","0.0.0.0","--port","8000") $BACKEND
Start-Svc "processor"           $ppy @("-m","uvicorn","main:app","--reload","--host","0.0.0.0","--port","8001") $PROC
Start-Svc "processor-worker"    $ppy @("worker.py") $PROC
Start-Svc "coordination"        $cpy @("-m","uvicorn","main:app","--reload","--host","0.0.0.0","--port","8002") $COORD
Start-Svc "coordination-worker" $cpy @("worker.py") $COORD

# frontend (pnpm via cmd so PATH resolves on Windows)
Start-Process -FilePath "cmd.exe" -ArgumentList @("/c","pnpm","dev","--host","127.0.0.1","--port","5173") `
  -WorkingDirectory $FRONT -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $LOGS "frontend.log") `
  -RedirectStandardError  (Join-Path $LOGS "frontend.err.log") | Out-Null
Write-Host "started frontend"

Write-Host ""
Write-Host "URLs: frontend http://localhost:5173 | backend :8000/docs | processor :8001 | coordination :8002/health"
