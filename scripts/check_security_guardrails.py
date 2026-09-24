#!/usr/bin/env python3
"""Script de verificação de integridade de testes de segurança com Guardrail Anti-Regressão.

Executado no pipeline de CI/CD para assegurar que nenhum desenvolvedor ou agente autônomo
de IA modifique ou delete testes protegidos por guardrails sem autorização formal.
"""

import json
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def is_override_granted() -> bool:
    """Verifica se há autorização explícita para modificação de testes protegidos."""
    # 1. Variável de ambiente direta
    if os.getenv("SECURITY_GUARDRAIL_OVERRIDE", "").lower() in ("true", "1", "yes"):
        return True

    # 2. Label no Pull Request (GitHub Actions)
    pr_labels_raw = os.getenv("PR_LABELS", "")
    if pr_labels_raw:
        try:
            labels = json.loads(pr_labels_raw)
            if isinstance(labels, list) and "security-guardrail-override" in labels:
                return True
        except Exception:
            if "security-guardrail-override" in pr_labels_raw:
                return True

    # 3. Mensagem de commit explícita
    commit_msg = os.getenv("COMMIT_MSG", "")
    if not commit_msg:
        try:
            commit_msg = subprocess.check_output(
                ["git", "log", "-1", "--pretty=%B"],
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            pass

    if "[security-guardrail-override: approved]" in commit_msg.lower():
        return True

    return False


def get_base_commit() -> str:
    """Determina o commit base para comparação do diff."""
    # Em pull_request no GitHub Actions: GITHUB_BASE_REF
    base_ref = os.getenv("GITHUB_BASE_REF")
    if base_ref:
        return f"origin/{base_ref}"

    # Tenta origin/main se existir
    try:
        subprocess.check_output(
            ["git", "rev-parse", "--verify", "origin/main"],
            stderr=subprocess.DEVNULL,
        )
        return "origin/main"
    except Exception:
        pass

    # Fallback para o commit anterior
    return "HEAD~1"


def check_guardrails() -> int:
    """Analisa o diff do git procurando alterações em testes protegidos."""
    if is_override_granted():
        print("🛡️ [SECURITY GATE] Autorização de modificação detectada (Override Ativo).")
        print("   Alterações em testes de guardrail permitidas para este commit/PR.")
        return 0

    base_commit = get_base_commit()
    print(f"🔍 [SECURITY GATE] Inspecionando diff contra base: {base_commit}")

    try:
        diff_cmd = [
            "git",
            "diff",
            "-U3",
            f"{base_commit}...HEAD",
            "--",
            "backend/tests/",
        ]
        diff_output = subprocess.check_output(
            diff_cmd, text=True, encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        # Se falhar (ex: shallow clone sem base), tenta diff direto com HEAD~1
        try:
            diff_cmd = ["git", "diff", "-U3", "HEAD~1", "--", "backend/tests/"]
            diff_output = subprocess.check_output(
                diff_cmd, text=True, encoding="utf-8", errors="replace", stderr=subprocess.DEVNULL
            )
        except Exception as exc:
            print(f"⚠️ [SECURITY GATE] Não foi possível obter git diff ({exc}). Prosseguindo com cautela.")
            return 0

    if not diff_output.strip():
        print("✅ [SECURITY GATE] Nenhum arquivo de teste foi modificado.")
        return 0

    # Marcadores estritos que definem um teste de segurança protegido
    GUARDRAIL_MARKERS = [
        "VETOR DE AMEAÇA:",
        "PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):",
        "COMPORTAMENTO ESPERADO (FAIL-CLOSED):",
        "RISCO DE REGRESSÃO SILENCIOSA",
    ]

    violations: list[str] = []
    current_file = ""
    in_protected_hunk = False
    modified_protected_lines = False

    for line in diff_output.splitlines():
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3].lstrip("b/")
            in_protected_hunk = False
            modified_protected_lines = False
            continue

        if line.startswith("@@"):
            # Novo hunk
            in_protected_hunk = False
            modified_protected_lines = False
            continue

        # Verifica se o contexto do hunk menciona guardrail de segurança
        if any(marker in line for marker in GUARDRAIL_MARKERS):
            in_protected_hunk = True

        # Se estamos dentro de um teste protegido e uma linha de código foi deletada ou alterada
        if in_protected_hunk:
            if line.startswith("-") and not line.startswith("---"):
                # Linha removida/modificada dentro de bloco protegido
                violations.append(f"Arquivo '{current_file}': linha removida/alterada -> {line[1:].strip()}")

    if violations:
        print("\n" + "=" * 80)
        print("❌ [SECURITY GATE FALHOU] ALTERAÇÃO NÃO AUTORIZADA EM TESTE DE SEGURANÇA PROTEGIDO!")
        print("=" * 80)
        print("Foram detectadas modificações em testes blindados com docstring de Guardrail Anti-Regressão:\n")
        for v in violations[:15]:
            print(f"  • {v}")
        if len(violations) > 15:
            print(f"  ... e mais {len(violations) - 15} ocorrências.")

        print("\n📋 PROTOCOLO OBRIGATÓRIO (AGENTS.MD / SECURITY-ANTIREGRESSION-GUARDRAILS):")
        print("  1. Agentes de IA/LLM são TERMINANTEMENTE PROIBIDOS de alterar esses testes sem permissão humana.")
        print("  2. Para autorizar formalmente esta alteração no repositório:")
        print("     - Inclua no commit: '[security-guardrail-override: approved]'")
        print("     - OU adicione a label no PR: 'security-guardrail-override'")
        print("=" * 80 + "\n")
        return 1

    print("✅ [SECURITY GATE] Nenhum teste de segurança protegido foi violado.")
    return 0


if __name__ == "__main__":
    sys.exit(check_guardrails())
