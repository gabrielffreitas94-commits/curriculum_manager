#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "===================================================================="
echo "  [ThothCVs AI] Inicialização Unificada do Sistema"
echo "===================================================================="
echo ""

# 1. Compilar Tailwind CSS
echo "[1/3] Compilando estilos Tailwind CSS..."
python3 scripts/build_css.py || python scripts/build_css.py
echo ""

# 2. Aplicar migrações do Alembic
echo "[2/3] Aplicando migrações do banco de dados..."
if command -v uv &> /dev/null; then
    uv --directory backend run alembic upgrade head
else
    (cd backend && python3 -m alembic upgrade head)
fi
echo ""

# 3. Iniciar Servidor FastAPI
echo "[3/3] Iniciando servidor FastAPI (ThothCVs AI)..."
echo "===================================================================="
echo "  * Aplicação Web:      http://127.0.0.1:8000"
echo "  * Swagger UI (Docs):  http://127.0.0.1:8000/api/v1/docs"
echo "  * Health Check:       http://127.0.0.1:8000/health"
echo "===================================================================="
echo "Pressione Ctrl+C para encerrar o servidor."
echo ""

if command -v uv &> /dev/null; then
    uv --directory backend run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
else
    cd backend && python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
fi
