$ErrorActionPreference = "Continue"
$baseDir = $PSScriptRoot
cd "$baseDir\frontend"
if (Test-Path ".next") {
    Remove-Item -Recurse -Force ".next"
}
npm run dev
