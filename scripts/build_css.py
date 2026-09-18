#!/usr/bin/env python3
"""Script para compilação prévia do Tailwind CSS sem dependência de Node.js/npm.

Utiliza o Tailwind Standalone CLI oficial da Tailwind Labs.
Suporta compilação para produção (--minify) ou modo de observação contínua (--watch).
"""

import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
TOOLS_DIR = BACKEND_DIR / "tools"
INPUT_CSS = BACKEND_DIR / "app" / "static" / "css" / "input.css"
OUTPUT_CSS = BACKEND_DIR / "app" / "static" / "css" / "styles.css"


def get_tailwind_cli_path() -> Path:
    """Garante que o executável standalone do Tailwind está presente, baixando se necessário."""
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        filename = "tailwindcss-windows-x64.exe"
        binary_path = TOOLS_DIR / "tailwindcss.exe"
    elif system == "darwin":
        filename = "tailwindcss-macos-arm64" if "arm" in machine else "tailwindcss-macos-x64"
        binary_path = TOOLS_DIR / "tailwindcss"
    else:
        filename = "tailwindcss-linux-arm64" if "arm" in machine else "tailwindcss-linux-x64"
        binary_path = TOOLS_DIR / "tailwindcss"

    if not binary_path.exists():
        url = f"https://github.com/tailwindlabs/tailwindcss/releases/latest/download/{filename}"
        print(f"📥 [Tailwind CLI] Baixando binário oficial standalone de {url}...")
        urllib.request.urlretrieve(url, binary_path)
        binary_path.chmod(0o755)
        print("✅ [Tailwind CLI] Download concluído com sucesso!")

    return binary_path


def build(minify: bool = True, watch: bool = False) -> None:
    """Compila o CSS de entrada gerando o styles.css otimizado."""
    cli_path = get_tailwind_cli_path()
    OUTPUT_CSS.parent.mkdir(parents=True, exist_ok=True)

    cmd = [str(cli_path), "-i", str(INPUT_CSS), "-o", str(OUTPUT_CSS)]

    if minify:
        cmd.append("--minify")
    if watch:
        cmd.append("--watch")

    print(f"🚀 [Tailwind CLI] Compilando CSS ({'watch' if watch else 'minify'})...")
    try:
        subprocess.run(cmd, cwd=str(BACKEND_DIR), check=True)
        if not watch:
            size_kb = OUTPUT_CSS.stat().st_size / 1024
            print(f"✨ [Tailwind CLI] CSS compilado com sucesso em '{OUTPUT_CSS}' ({size_kb:.1f} KB)!")
    except KeyboardInterrupt:
        print("\n🛑 [Tailwind CLI] Modo watch encerrado.")


if __name__ == "__main__":
    is_watch = "--watch" in sys.argv
    build(minify=not is_watch, watch=is_watch)
