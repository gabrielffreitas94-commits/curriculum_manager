#!/usr/bin/env python3
"""Script multiplataforma para inicialização completa do ThothCVs AI."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
SCRIPTS_DIR = ROOT_DIR / "scripts"


def run_cmd(cmd: list[str], cwd: Path | None = None) -> None:
    """Executa um comando no terminal tratando interrupções do usuário."""
    subprocess.run(cmd, cwd=str(cwd or ROOT_DIR), check=True)


def main() -> None:
    """Orquestra a inicialização do ThothCVs AI."""
    print("=" * 68)
    print("  [ThothCVs AI] Inicialização Unificada do Sistema")
    print("=" * 68)
    print()

    # 1. Compilar Tailwind CSS
    print("[1/3] Compilando estilos Tailwind CSS...")
    build_css_script = SCRIPTS_DIR / "build_css.py"
    if build_css_script.exists():
        run_cmd([sys.executable, str(build_css_script)])
    print()

    # 2. Migrações do Banco de Dados
    print("[2/3] Aplicando migrações do banco de dados...")
    has_uv = shutil.which("uv") is not None
    if has_uv:
        run_cmd(["uv", "--directory", "backend", "run", "alembic", "upgrade", "head"])
    else:
        run_cmd([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR)
    print()

    # 3. Iniciar Servidor FastAPI
    print("[3/3] Iniciando servidor FastAPI (ThothCVs AI)...")
    print("=" * 68)
    print("  * Aplicação Web:      http://127.0.0.1:8000")
    print("  * Swagger UI (Docs):  http://127.0.0.1:8000/api/v1/docs")
    print("  * Health Check:       http://127.0.0.1:8000/health")
    print("=" * 68)
    print("Pressione Ctrl+C para encerrar o servidor.\n")

    if has_uv:
        run_cmd(
            [
                "uv",
                "--directory",
                "backend",
                "run",
                "uvicorn",
                "app.main:app",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ]
        )
    else:
        run_cmd(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=BACKEND_DIR,
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Servidor ThothCVs AI encerrado pelo usuário.")
        sys.exit(0)
