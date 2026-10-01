$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is not installed. Install it from https://docs.astral.sh/uv/getting-started/installation/ and rerun this script."
}

uv sync --project backend --extra dev
Push-Location frontend
try {
    npm ci
} finally {
    Pop-Location
}

Write-Host "Checkpoint 1 dependencies are ready. Copy .env.example to backend/.env and add only a replacement OpenRouter key."
