#!/usr/bin/env python3
"""Script multiplataforma para inicialização completa do ThothCVs AI."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Suporte à execução a partir da raiz ou do diretório backend/
script_dir = Path(__file__).resolve().parent
if script_dir.name == "backend":
    ROOT_DIR = script_dir.parent
elif (Path.cwd() / "backend").exists():
    ROOT_DIR = Path.cwd()
elif Path.cwd().name == "backend":
    ROOT_DIR = Path.cwd().parent
else:
    ROOT_DIR = script_dir

BACKEND_DIR = ROOT_DIR / "backend"
SCRIPTS_DIR = ROOT_DIR / "scripts"


def run_cmd(cmd: list[str], cwd: Path | None = None) -> None:
    """Executa um comando no terminal tratando interrupções do usuário."""
    subprocess.run(cmd, cwd=str(cwd or ROOT_DIR), check=True)


def free_port(port: int = 8000) -> None:
    """Libera a porta caso esteja travada por algum processo zumbi anterior."""
    if sys.platform == "win32":
        try:
            cmd = (
                f'powershell -Command "$conns = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue; '
                f'if ($conns) {{ foreach ($c in $conns) {{ Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }} }}"'
            )
            subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
        except Exception:
            pass


def main() -> None:
    """Orquestra a inicialização do ThothCVs AI."""
    print("=" * 68)
    print("  [ThothCVs AI] Inicialização Unificada do Sistema")
    print("=" * 68)
    print()

    # 0. Liberar porta 8000 de instâncias anteriores
    free_port(8000)

    # 1. Compilar Tailwind CSS
    print("[1/3] Compilando estilos Tailwind CSS...")
    build_css_script = SCRIPTS_DIR / "build_css.py"
    if build_css_script.exists():
        try:
            run_cmd([sys.executable, str(build_css_script)])
        except Exception as exc:
            print(f"[AVISO] Falha ao compilar CSS com Python padrão ({exc}). Tentando ambiente virtual...")
            venv_python = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
            if venv_python.exists():
                run_cmd([str(venv_python), str(build_css_script)])
    print()

    # 2. Migrações do Banco de Dados
    print("[2/3] Aplicando migrações do banco de dados...")
    has_uv = shutil.which("uv") is not None
    if has_uv:
        run_cmd(["uv", "--directory", str(BACKEND_DIR), "run", "alembic", "upgrade", "head"])
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
                str(BACKEND_DIR),
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
        free_port(8000)
        sys.exit(0)
