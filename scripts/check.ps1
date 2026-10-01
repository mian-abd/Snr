$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

uv run --project backend ruff check backend/app backend/tests
uv run --project backend mypy backend/app
uv run --project backend pytest backend/tests -q

Push-Location frontend
try {
    npm run lint
    npm test
    npm run build
} finally {
    Pop-Location
}

Write-Host "All Checkpoint 1 checks passed."
