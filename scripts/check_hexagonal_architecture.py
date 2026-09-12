#!/usr/bin/env python3
"""Guardrail Automatizado de Arquitetura Hexagonal (AST Import Linter).

Inspeciona estaticamente a árvore sintática (AST) de todos os arquivos Python
em 'backend/app' para garantir a conformidade estrita com os limites de camada
da Arquitetura Hexagonal (Ports & Adapters) e Inversão de Dependências (DIP).
"""

import ast
import os
import sys
from dataclasses import dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


@dataclass(frozen=True)
class Violation:
    file_path: Path
    line_number: int
    imported_module: str
    rule_name: str
    description: str


# Regras de isolamento estrito por camada hexagonal
LAYER_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "domain": {
        "disallowed_prefixes": (
            "app.ports",
            "app.services",
            "app.adapters",
            "app.api",
            "app.main",
            "fastapi",
            "google.genai",
            "weasyprint",
            "firebase_admin",
            "docx",
        ),
        "description": "O domínio deve ser puro e nunca depender de portas, serviços, adaptadores ou frameworks externos.",
    },
    "ports": {
        "disallowed_prefixes": (
            "app.services",
            "app.adapters",
            "app.api",
            "app.main",
            "fastapi",
            "google.genai",
            "weasyprint",
            "firebase_admin",
            "docx",
        ),
        "description": "As portas são contratos abstratos puros e não podem importar adaptadores, serviços ou SDKs proprietários.",
    },
    "services": {
        "disallowed_prefixes": (
            "app.adapters",
            "app.main",
        ),
        "description": "Os serviços orquestram casos de uso via injeção de portas e nunca devem importar adaptadores concretos diretamente.",
    },
    "core": {
        "disallowed_prefixes": (
            "app.adapters",
            "app.services",
            "app.api",
            "app.main",
        ),
        "description": "O core é a base transversal e não pode se acoplar a adaptadores, serviços ou controladores HTTP.",
    },
    "adapters": {
        "disallowed_prefixes": (
            "app.services",
            "app.api",
            "app.main",
        ),
        "description": "Os adaptadores implementam portas e não devem depender de serviços de negócio ou rotas HTTP.",
    },
    "endpoints": {
        "disallowed_prefixes": (
            "app.adapters",
            "app.main",
        ),
        "description": "Os controladores de API (endpoints) devem consumir casos de uso ou portas via DI, sem importar adaptadores concretos.",
    },
}

# Débitos técnicos herdados catalogados para refatoração arquitetural controlada.
# Qualquer nova violação ou novo arquivo que viole as regras causará falha imediata no CI.
LEGACY_DEBT_BASELINE: set[tuple[str, str]] = {
    ("app/services/document_service.py", "app.adapters.docx_adapter"),
    ("app/services/document_service.py", "app.adapters.docx_adapter.DocxAdapter"),
    ("app/services/document_service.py", "app.adapters.weasyprint_adapter"),
    ("app/services/document_service.py", "app.adapters.weasyprint_adapter.WeasyPrintAdapter"),
    ("app/services/resume_service.py", "app.adapters.gemini_ai_adapter"),
    ("app/services/resume_service.py", "app.adapters.gemini_ai_adapter.GeminiAIAdapter"),
}


def get_layer(relative_path: Path) -> str | None:
    """Identifica a camada arquitetural a partir do caminho relativo."""
    # Normaliza separadores de caminho para comparação consistente
    normalized = relative_path.as_posix()
    if normalized.startswith("app/api/v1/endpoints/"):
        return "endpoints"
    parts = relative_path.parts
    if len(parts) >= 2 and parts[0] == "app":
        layer = parts[1]
        if layer in LAYER_RULES:
            return layer
    return None


def extract_imports(tree: ast.AST) -> list[tuple[int, str]]:
    """Extrai todos os módulos importados e seus respectivos números de linha."""
    imported_modules: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.append((node.lineno, node.module))
                for alias in node.names:
                    imported_modules.append((node.lineno, f"{node.module}.{alias.name}"))

    return imported_modules


def audit_hexagonal_architecture(app_dir: Path) -> tuple[list[Violation], list[Violation]]:
    """Varre recursivamente os arquivos Python e audita conformidade arquitetural.

    Returns:
        tuple[list[Violation], list[Violation]]: (violações bloqueantes, débitos legados catalogados).
    """
    blocking_violations: list[Violation] = []
    legacy_debts: list[Violation] = []

    for py_file in sorted(app_dir.rglob("*.py")):
        rel_path = py_file.relative_to(app_dir.parent)
        layer = get_layer(rel_path)
        if not layer:
            continue

        rules = LAYER_RULES[layer]
        disallowed = rules["disallowed_prefixes"]
        description = rules["description"]

        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except Exception as err:
            print(f"⚠️ Erro ao analisar sintaxe de {py_file}: {err}", file=sys.stderr)
            continue

        posix_path = rel_path.as_posix()
        for lineno, module_name in extract_imports(tree):
            for bad_prefix in disallowed:
                if module_name == bad_prefix or module_name.startswith(f"{bad_prefix}."):
                    violation = Violation(
                        file_path=rel_path,
                        line_number=lineno,
                        imported_module=module_name,
                        rule_name=f"LAYER_ISOLATION_{layer.upper()}",
                        description=description,
                    )
                    if (posix_path, module_name) in LEGACY_DEBT_BASELINE:
                        legacy_debts.append(violation)
                    else:
                        blocking_violations.append(violation)

    return blocking_violations, legacy_debts


def main() -> int:
    """Executa a verificação e reporta violações arquiteturais."""
    repo_root = Path(__file__).resolve().parent.parent
    app_dir = repo_root / "backend" / "app"

    if not app_dir.exists():
        print(f"❌ Diretório da aplicação não encontrado: {app_dir}", file=sys.stderr)
        return 1

    print("🔍 [ARCHITECTURE GATE] Auditando conformidade com a Arquitetura Hexagonal...")
    blocking_violations, legacy_debts = audit_hexagonal_architecture(app_dir)

    if legacy_debts:
        print(f"\n⚠️  [ARCHITECTURE GATE] {len(legacy_debts)} débito(s) técnico(s) legado(s) registrado(s) para refatoração:")
        for d in legacy_debts:
            print(f"  🔸 {d.file_path.as_posix()}:{d.line_number} -> '{d.imported_module}'")

    if blocking_violations:
        print(f"\n❌ [ARCHITECTURE GATE] {len(blocking_violations)} NOVA(S) VIOLAÇÃO(ÕES) ARQUITETURAL(IS) DETECTADA(S):\n")
        for v in blocking_violations:
            print(f"  🚨 {v.file_path}:{v.line_number}")
            print(f"     Import proibido: '{v.imported_module}'")
            print(f"     Regra: {v.rule_name} — {v.description}\n")
        print("💡 Dica: Utilize Inversão de Dependência (DIP) injetando Portas em vez de importar diretamente.\n")
        return 1

    print("\n✅ [ARCHITECTURE GATE] 100% em conformidade com os limites da Arquitetura Hexagonal (0 novas violações)!\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
