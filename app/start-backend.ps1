$ErrorActionPreference = "Stop"
$BackendPath = Join-Path $PSScriptRoot "backend"
$VenvPath = Join-Path $BackendPath ".venv"

if (-not (Test-Path -LiteralPath $VenvPath)) {
  python -m venv $VenvPath
}

& (Join-Path $VenvPath "Scripts\Activate.ps1")
pip install -r (Join-Path $BackendPath "requirements.txt")
$env:DATABASE_URL = if ($env:DATABASE_URL) { $env:DATABASE_URL } else { "postgresql://postgres@localhost:5432/vendas" }
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir $BackendPath
