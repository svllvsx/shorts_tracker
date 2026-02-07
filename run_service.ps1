param(
    [switch]$Reload
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "python not found at $python"
}

if ($Reload) {
    & $python -m uvicorn app.main:app --reload
} else {
    & $python -m uvicorn app.main:app
}
