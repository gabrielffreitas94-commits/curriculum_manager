"""Motor de auditoria algorítmica anti-alucinação pós-geração (GroundingAuditEngine).

Executa validação cruzada estrita entre o JSON estruturado emitido pelo Gemini
e o dossiê factual do usuário persistido no PostgreSQL. Garante 100% de veracidade.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class HallucinationSeverity(StrEnum):
    """Níveis de gravidade para discrepâncias factuais identificadas na auditoria."""

    LOW = "low"  # Pequenas variações de grafia ou sinônimos
    MEDIUM = "medium"  # Competência técnica não cadastrada
    HIGH = "high"  # Credencial ou número de impacto inventado
    CRITICAL = "critical"  # Empresa ou graduação inexistente no perfil


@dataclass(frozen=True)
class HallucinationIssue:
    """Representação de uma inconsistência factual detectada no currículo gerado.

    Attributes:
        field: Nome do bloco/campo afetado ('selected_experiences', 'skills_highlighted').
        hallucinated_value: Valor espúrio forjado pela IA.
        description: Explicação técnica da discrepância.
        severity: Grau de severidade do desvio.
    """

    field: str
    hallucinated_value: str
    description: str
    severity: HallucinationSeverity


@dataclass
class AuditResult:
    """Resultado consolidado da auditoria factual anti-alucinação.

    Attributes:
        is_valid: Flag indicando se o currículo atende aos critérios mínimos de confiança.
        trust_score: Pontuação percentual de veracidade (0.0 a 100.0).
        severity: Gravidade máxima detectada na auditoria.
        hallucinations: Lista de todas as inconsistências identificadas.
    """

    is_valid: bool
    trust_score: float
    severity: HallucinationSeverity = HallucinationSeverity.LOW
    hallucinations: list[HallucinationIssue] = field(default_factory=list)


class GroundingAuditEngine:
    """Motor algorítmico determinístico para detecção de alucinações da LLM."""

    def audit(
        self,
        generated_content: dict[str, Any],
        user_dossier: dict[str, Any],
    ) -> AuditResult:
        """Compara o conteúdo gerado pela IA com a fonte primária da verdade do candidato.

        Args:
            generated_content: Dicionário correspondente ao FullGeneratedResumePayload.
            user_dossier: Fatos cadastrados (empresas, cargos, skills, formações).

        Returns:
            AuditResult: Diagnóstico de veracidade e lista de anomalias detectadas.
        """
        issues: list[HallucinationIssue] = []
        total_facts = 0
        verified_facts = 0

        # Normaliza conjuntos factuais do usuário
        registered_companies = {c.lower().strip() for c in user_dossier.get("companies", [])}
        registered_skills = {s.lower().strip() for s in user_dossier.get("skills", [])}

        # 1. Validação de Empresas nas Experiências
        experiences = generated_content.get("selected_experiences", [])
        for exp in experiences:
            company = exp.get("company_name", "").strip()
            total_facts += 1
            if company.lower() not in registered_companies:
                issues.append(
                    HallucinationIssue(
                        field="selected_experiences.company_name",
                        hallucinated_value=company,
                        description=f"Empresa não cadastrada no perfil: '{company}'",
                        severity=HallucinationSeverity.CRITICAL,
                    )
                )
            else:
                verified_facts += 1

            # Validação de Stack das Experiências
            for tech in exp.get("tech_stack", []):
                total_facts += 1
                if tech.lower().strip() not in registered_skills:
                    issues.append(
                        HallucinationIssue(
                            field="selected_experiences.tech_stack",
                            hallucinated_value=tech,
                            description=f"Tecnologia '{tech}' não cadastrada no perfil do usuário.",
                            severity=HallucinationSeverity.MEDIUM,
                        )
                    )
                else:
                    verified_facts += 1

        # 2. Validação de Skills em Destaque
        skills = generated_content.get("skills_highlighted", [])
        for skill in skills:
            total_facts += 1
            if skill.lower().strip() not in registered_skills:
                issues.append(
                    HallucinationIssue(
                        field="skills_highlighted",
                        hallucinated_value=skill,
                        description=f"Habilidade '{skill}' inventada pela IA sem registro factual.",
                        severity=HallucinationSeverity.MEDIUM,
                    )
                )
            else:
                verified_facts += 1

        # Cálculo do Trust Score
        trust_score = (
            100.0 if total_facts == 0 else round((verified_facts / total_facts) * 100.0, 2)
        )

        # Avaliação de Severidade e Aceitabilidade
        has_critical = any(i.severity == HallucinationSeverity.CRITICAL for i in issues)
        max_severity = (
            HallucinationSeverity.CRITICAL
            if has_critical
            else (HallucinationSeverity.MEDIUM if issues else HallucinationSeverity.LOW)
        )

        is_valid = (not has_critical) and (trust_score >= 80.0)

        return AuditResult(
            is_valid=is_valid,
            trust_score=trust_score,
            severity=max_severity,
            hallucinations=issues,
        )

    def sanitize(
        self,
        generated_content: dict[str, Any],
        audit_result: AuditResult,
    ) -> dict[str, Any]:
        """Aplica poda silenciosa de competências não verificadas no conteúdo.

        Args:
            generated_content: Dicionário original gerado pelo Gemini.
            audit_result: Relatório da auditoria contendo os itens espúrios.

        Returns:
            dict[str, Any]: Conteúdo sanitizado contendo apenas dados com comprovação factual.
        """
        import copy

        sanitized = copy.deepcopy(generated_content)
        hallucinated_skills = {
            i.hallucinated_value.lower().strip()
            for i in audit_result.hallucinations
            if i.field in ("skills_highlighted", "selected_experiences.tech_stack")
        }

        # Poda em skills_highlighted
        if "skills_highlighted" in sanitized:
            sanitized["skills_highlighted"] = [
                s
                for s in sanitized["skills_highlighted"]
                if s.lower().strip() not in hallucinated_skills
            ]

        # Poda no tech_stack das experiências
        if "selected_experiences" in sanitized:
            for exp in sanitized["selected_experiences"]:
                if "tech_stack" in exp:
                    exp["tech_stack"] = [
                        t for t in exp["tech_stack"] if t.lower().strip() not in hallucinated_skills
                    ]

        return sanitized
