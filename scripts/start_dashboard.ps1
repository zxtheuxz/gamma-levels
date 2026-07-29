$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$dashboardRoot = Join-Path $projectRoot "dashboard"

python -c "import fastapi, uvicorn, httpx" 2>$null
if ($LASTEXITCODE -ne 0) {
    python -m pip install -e $projectRoot
}

if (-not (Test-Path (Join-Path $dashboardRoot "node_modules"))) {
    Push-Location $dashboardRoot
    try {
        npm install --ignore-scripts --no-audit --no-fund
    }
    finally {
        Pop-Location
    }
}

$backendListening = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($backendListening) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2
        if ($health.version -ne "0.3.3") {
            $backendListening | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
            $backendListening = $null
        }
    }
    catch {
        $backendListening | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
        $backendListening = $null
    }
}
if (-not $backendListening) {
    Start-Process -FilePath "python" `
        -ArgumentList @("-m", "uvicorn", "gamma_levels.api:app", "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null
}

$frontendListening = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if (-not $frontendListening) {
    Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") `
        -WorkingDirectory $dashboardRoot -WindowStyle Hidden | Out-Null
}

$deadline = (Get-Date).AddSeconds(60)
do {
    try {
        $backendReady = (Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200
    }
    catch {
        $backendReady = $false
    }
    try {
        $frontendReady = (Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200
    }
    catch {
        $frontendReady = $false
    }
    if (-not ($backendReady -and $frontendReady)) {
        Start-Sleep -Milliseconds 500
    }
} while ((Get-Date) -lt $deadline -and -not ($backendReady -and $frontendReady))

if (-not $backendReady) { throw "O motor de cálculos não iniciou na porta 8000." }
if (-not $frontendReady) { throw "O dashboard não iniciou na porta 3000." }

Start-Process "http://localhost:3000"
