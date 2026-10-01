$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

uv run --project backend python backend/scripts/export_openapi.py
npx --prefix frontend openapi-typescript frontend/openapi.json -o frontend/src/api/schema.d.ts
