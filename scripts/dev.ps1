$ErrorActionPreference = "Stop"

$backend = Start-Process uv -ArgumentList @("run", "--project", "backend", "uvicorn", "app.main:app", "--app-dir", "backend", "--reload", "--port", "8000") -PassThru -WindowStyle Hidden
$frontend = Start-Process npm -ArgumentList @("--prefix", "frontend", "run", "dev", "--", "--host", "127.0.0.1") -PassThru -WindowStyle Hidden

Write-Host "Backend: http://127.0.0.1:8000"
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "Press Ctrl+C to stop both processes."

try {
    Wait-Process -Id @($backend.Id, $frontend.Id)
} finally {
    Stop-Process -Id @($backend.Id, $frontend.Id) -Force -ErrorAction SilentlyContinue
}
