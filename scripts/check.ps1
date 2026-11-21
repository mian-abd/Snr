$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

uv run --project backend ruff check backend/app backend/tests
uv run --project backend python -m mypy --config-file backend/pyproject.toml backend/app
uv run --project backend pytest backend/tests -q
uv run --project backend python -m app.learned.validate

Push-Location frontend
try {
    npm run lint
    npm test
    npm run build
} finally {
    Pop-Location
}

Write-Host "All checks passed."
