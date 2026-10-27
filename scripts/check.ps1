$ErrorActionPreference = 'Stop'

$python = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw 'Ambiente virtual não encontrado. Execute: python -m venv .venv'
}

Push-Location (Join-Path $PSScriptRoot '..')
try {
    & $python -m unittest discover -s . -p 'test_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'Falha nos testes do scraper.' }
}
finally {
    Pop-Location
}
