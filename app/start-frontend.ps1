$ErrorActionPreference = "Stop"
$FrontendPath = Join-Path $PSScriptRoot "frontend"
$env:BACKEND_INTERNAL_URL = if ($env:BACKEND_INTERNAL_URL) { $env:BACKEND_INTERNAL_URL } else { "http://127.0.0.1:8000" }
Set-Location -LiteralPath $FrontendPath
if (-not (Test-Path -LiteralPath (Join-Path $FrontendPath "node_modules"))) {
  npm install
}
npm run dev -- --hostname 0.0.0.0 --port 3000
