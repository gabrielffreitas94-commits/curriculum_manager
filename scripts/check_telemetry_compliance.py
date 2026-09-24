#!/usr/bin/env python3
"""Guardrail Automatizado de Observabilidade e Telemetria (Zero Blind Spots Linter).

Inspeciona estaticamente a árvore sintática (AST) de todos os arquivos Python em
'backend/app/adapters', 'backend/app/services' e 'backend/app/api' para garantir
que nenhum código novo nasça sem instrumentação estruturada (get_logger).
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
class TelemetryViolation:
    file_path: Path
    rule_name: str
    description: str


# Arquivos de infraestrutura de logging e injeção de dependências isentos
EXCLUDED_INFRA_FILES: set[str] = {
    "app/adapters/gcp_logging_adapter.py",  # Processador nativo do structlog/GCP
    "app/api/v1/deps.py",  # Injetor de dependências FastAPI
}

# Débitos técnicos legados documentados antes da instituição da Regra de Zero Pontos Cegos
LEGACY_TELEMETRY_EXCEPTIONS: set[str] = {
    "app/adapters/firebase_auth_adapter.py",
    "app/services/application_service.py",
    "app/services/document_service.py",
    "app/services/notification_service.py",
    "app/services/profile_service.py",
    "app/services/user_service.py",
    "app/api/v1/applications.py",
    "app/api/v1/auth.py",
    "app/api/v1/health.py",
    "app/api/v1/notifications.py",
    "app/api/v1/profile.py",
    "app/api/v1/resumes.py",
    "app/api/v1/users.py",
}


def check_module_telemetry(file_path: Path, app_root: Path) -> list[TelemetryViolation]:
    """Inspeciona um módulo Python verificando se instancia logger estruturado."""
    violations: list[TelemetryViolation] = []

    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as exc:
        violations.append(
            TelemetryViolation(
                file_path=file_path,
                rule_name="SyntaxError",
                description=f"Falha ao realizar parsing AST: {exc}",
            )
        )
        return violations

    imports_get_logger = False
    instantiates_logger = False

    for node in ast.walk(tree):
        # Verifica se importou get_logger
        if isinstance(node, ast.ImportFrom):
            if node.module and "logging" in node.module:
                for alias in node.names:
                    if alias.name == "get_logger":
                        imports_get_logger = True
        # Verifica se invocou get_logger(...)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "get_logger":
                instantiates_logger = True
            elif isinstance(func, ast.Attribute) and func.attr == "get_logger":
                instantiates_logger = True

    if not (imports_get_logger and instantiates_logger):
        rel_path = file_path.relative_to(app_root).as_posix()
        violations.append(
            TelemetryViolation(
                file_path=file_path,
                rule_name="MissingStructuredLogger",
                description=(
                    f"O módulo '{rel_path}' não importa ou não instancia logger estruturado via "
                    f"'get_logger(...)'. Todo novo adapter, service ou router deve possuir telemetria."
                ),
            )
        )

    return violations


def audit_telemetry(repo_root: Path) -> tuple[list[TelemetryViolation], list[TelemetryViolation]]:
    """Varre adapters, services e routers auditando conformidade de observabilidade.

    Returns:
        tuple[list[TelemetryViolation], list[TelemetryViolation]]:
            (novas_violações, débitos_legados)
    """
    app_root = repo_root / "backend" / "app"
    if not app_root.exists():
        app_root = repo_root / "app"

    target_dirs = [
        app_root / "adapters",
        app_root / "services",
        app_root / "api",
    ]

    new_violations: list[TelemetryViolation] = []
    legacy_violations: list[TelemetryViolation] = []

    for target_dir in target_dirs:
        if not target_dir.exists():
            continue
        for py_file in target_dir.rglob("*.py"):
            if py_file.name == "__init__.py" or "schemas" in py_file.parts:
                continue

            rel_posix = py_file.relative_to(app_root.parent).as_posix()
            if rel_posix in EXCLUDED_INFRA_FILES:
                continue

            file_violations = check_module_telemetry(py_file, app_root.parent)

            for v in file_violations:
                if rel_posix in LEGACY_TELEMETRY_EXCEPTIONS:
                    legacy_violations.append(v)
                else:
                    new_violations.append(v)

    return new_violations, legacy_violations


def main() -> int:
    """Ponto de entrada do script de verificação de telemetria."""
    repo_root = Path(__file__).resolve().parent.parent
    app_root = repo_root / "backend" / "app"
    if not app_root.exists():
        app_root = repo_root / "app"

    print("🔍 [TELEMETRY GATE] Auditando conformidade de observabilidade (Zero Pontos Cegos)...\n")

    new_violations, legacy_violations = audit_telemetry(repo_root)

    if legacy_violations:
        print(f"⚠️  [TELEMETRY GATE] {len(legacy_violations)} débito(s) técnico(s) legado(s) registrado(s):")
        for v in sorted(legacy_violations, key=lambda x: str(x.file_path)):
            rel = v.file_path.relative_to(app_root.parent).as_posix()
            print(f"  🔸 {rel} -> {v.rule_name}")
        print()

    if new_violations:
        print("=" * 80)
        print("❌ [TELEMETRY GATE FALHOU] PONTO(S) CEGO(S) DE TELEMETRIA DETECTADO(S)!")
        print("=" * 80)
        print("Os seguintes módulos violam a 'Regra Obrigatória de Observabilidade e Telemetria':\n")
        for v in new_violations:
            rel = v.file_path.relative_to(app_root.parent).as_posix()
            print(f"  • {rel}")
            print(f"    Descrição: {v.description}\n")

        print("📋 PROTOCOLO OBRIGATÓRIO (AGENTS.MD):")
        print("  1. Todo novo adapter, service ou router deve instanciar 'logger = get_logger(...)'.")
        print("  2. Operações I/O externas devem mensurar latência e registrar eventos estruturados.")
        print("=" * 80 + "\n")
        return 1

    print("✅ [TELEMETRY GATE] 100% em conformidade com as regras de observabilidade (0 novas violações)!\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
