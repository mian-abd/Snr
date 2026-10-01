$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

Push-Location frontend
try {
    npm run build
} finally {
    Pop-Location
}

Write-Host "Serving Adaptive LLM Router at http://127.0.0.1:8000"
uv run --project backend uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
