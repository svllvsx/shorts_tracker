param(
    [switch]$Reload
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$uvicorn = Join-Path $PSScriptRoot '.venv\Scripts\uvicorn.exe'
if (-not (Test-Path $uvicorn)) {
    throw "uvicorn not found at $uvicorn"
}

if ($Reload) {
    & $uvicorn app.main:app --reload
} else {
    & $uvicorn app.main:app
}
