@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ====================================================================
echo   [ThothCVs AI] Inicialização Unificada do Sistema
echo ====================================================================
echo.

cd /d "%~dp0"

:: 1. Compilar Tailwind CSS
echo [1/3] Compilando estilos Tailwind CSS...
python scripts\build_css.py
if errorlevel 1 (
    echo [AVISO] Tentando compilar CSS com ambiente virtual...
    if exist "backend\.venv\Scripts\python.exe" (
        backend\.venv\Scripts\python.exe scripts\build_css.py
    )
)
echo.

:: 2. Aplicar migrações do Alembic
echo [2/3] Aplicando migrações do banco de dados...
where uv >nul 2>&1
if %errorlevel% equ 0 (
    uv --directory backend run alembic upgrade head
) else (
    if exist "backend\.venv\Scripts\alembic.exe" (
        cd backend
        ..\backend\.venv\Scripts\alembic.exe upgrade head
        cd ..
    ) else (
        echo [ERRO] Nem 'uv' nem o ambiente virtual foram encontrados!
        exit /b 1
    )
)
echo.

:: 3. Iniciar Servidor FastAPI com Uvicorn
echo [3/3] Iniciando servidor FastAPI (ThothCVs AI)...
echo ====================================================================
echo   * Aplicação Web:      http://127.0.0.1:8000
echo   * Swagger UI (Docs):  http://127.0.0.1:8000/api/v1/docs
echo   * Health Check:       http://127.0.0.1:8000/health
echo ====================================================================
echo Pressione Ctrl+C para encerrar o servidor.
echo.

where uv >nul 2>&1
if %errorlevel% equ 0 (
    uv --directory backend run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) else (
    cd backend
    ..\backend\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
    cd ..
)
