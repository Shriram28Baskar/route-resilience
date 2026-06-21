$ErrorActionPreference = "Continue"
$baseDir = $PSScriptRoot
cd "$baseDir\backend"
$env:PYTHONPATH = "$baseDir\backend"
& "$baseDir\backend\.venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port 8000
