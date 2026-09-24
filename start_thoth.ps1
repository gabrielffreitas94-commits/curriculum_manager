<#
.SYNOPSIS
    Script unificado de inicialização do ThothCVs AI.
.DESCRIPTION
    Compila os estilos CSS com o Tailwind CLI standalone,
    aplica as migrações mais recentes do Alembic no SQLite/PostgreSQL
    e sobe o servidor FastAPI com recarregamento automático (reload).
#>

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "  [ThothCVs AI] Inicialização Unificada do Sistema" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Compilar Tailwind CSS
Write-Host "[1/3] Compilando estilos Tailwind CSS..." -ForegroundColor Yellow
try {
    python scripts/build_css.py
} catch {
    if (Test-Path "backend/.venv/Scripts/python.exe") {
        & "backend/.venv/Scripts/python.exe" scripts/build_css.py
    } else {
        Write-Warning "Não foi possível compilar o CSS. Continuando com versão existente..."
    }
}
Write-Host ""

# 2. Aplicar migrações do Alembic
Write-Host "[2/3] Aplicando migrações do banco de dados..." -ForegroundColor Yellow
$hasUv = Get-Command uv -ErrorAction SilentlyContinue

if ($hasUv) {
    uv --directory backend run alembic upgrade head
} elseif (Test-Path "backend/.venv/Scripts/alembic.exe") {
    Push-Location backend
    try {
        & "../backend/.venv/Scripts/alembic.exe" upgrade head
    } finally {
        Pop-Location
    }
} else {
    Write-Error "Nem o comando 'uv' nem o ambiente virtual 'backend/.venv' foram localizados."
}
Write-Host ""

# 3. Iniciar Servidor FastAPI
Write-Host "[3/3] Iniciando servidor FastAPI (ThothCVs AI)..." -ForegroundColor Green
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "  * Aplicação Web:      http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  * Swagger UI (Docs):  http://127.0.0.1:8000/api/v1/docs" -ForegroundColor White
Write-Host "  * Health Check:       http://127.0.0.1:8000/health" -ForegroundColor White
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "Pressione Ctrl+C para encerrar o servidor.`n" -ForegroundColor DarkGray

if ($hasUv) {
    uv --directory backend run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
} else {
    Push-Location backend
    try {
        & "../backend/.venv/Scripts/uvicorn.exe" app.main:app --reload --host 127.0.0.1 --port 8000
    } finally {
        Pop-Location
    }
}
