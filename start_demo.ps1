$ErrorActionPreference = "Stop"

Write-Host "[*] Starting Route Resilience Hackathon Demo..." -ForegroundColor Cyan

$baseDir = Get-Location

# Start Backend
Write-Host "[*] Starting FastAPI Backend..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$baseDir\start_backend.ps1" -WindowStyle Normal

Start-Sleep -Seconds 3

# Start Frontend
Write-Host "[*] Starting Next.js Frontend..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$baseDir\start_frontend.ps1" -WindowStyle Normal

Write-Host "[!] Both servers are starting up!" -ForegroundColor Green
Write-Host "[*] Frontend should be available at: http://localhost:3000" -ForegroundColor Green
Write-Host "[*] Backend API should be available at: http://127.0.0.1:8000" -ForegroundColor Green
