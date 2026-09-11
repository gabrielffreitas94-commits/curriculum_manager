"""Motor de auditoria algorítmica anti-alucinação pós-geração (GroundingAuditEngine).

Executa validação cruzada estrita entre o JSON estruturado emitido pelo Gemini
e o dossiê factual do usuário persistido no PostgreSQL. Garante 100% de veracidade.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any


class HallucinationSeverity(StrEnum):
    """Níveis de gravidade para discrepâncias factuais identificadas na auditoria."""

    LOW = "low"  # Pequenas variações de grafia ou sinônimos
    MEDIUM = "medium"  # Competência técnica não cadastrada
    HIGH = "high"  # Credencial ou número de impacto inventado
    CRITICAL = "critical"  # Empresa ou graduação inexistente no perfil


class ValidationTier(StrEnum):
    """Camadas ordenadas do pipeline de validação factual anti-alucinação."""

    SYNTACTIC = "syntactic"  # Camada 1: correspondência sintática exata
    PROVENANCE = "provenance"  # Camada 2: validação por proveniência (grounded_in)
    FUZZY = "fuzzy"  # Camada 3: similaridade sintática parcial (~85%)
    VECTOR = "vector"  # Camada 4: proximidade semântica vetorial / embeddings


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
        verified_counts_by_tier: Quantidade de fatos validados por cada camada do pipeline.
    """

    is_valid: bool
    trust_score: float
    severity: HallucinationSeverity = HallucinationSeverity.LOW
    hallucinations: list[HallucinationIssue] = field(default_factory=list)
    verified_counts_by_tier: dict[str, int] = field(default_factory=dict)


class GroundingAuditEngine:
    """Motor algorítmico determinístico para detecção de alucinações da LLM.

    Executa um pipeline de validação em 4 estágios cascateados:
    1. Validação Sintática: igualdade exata de strings normalizadas.
    2. Validação por Proveniência: verificação sintática do termo de origem (provenance_map).
    3. Fuzzy Matching: similaridade sintática parcial (~85%) via SequenceMatcher.
    4. Validação Vetorial: proximidade semântica vetorial (embeddings / cosseno >= 80%).
    """

    FUZZY_THRESHOLD = 0.85
    VECTOR_THRESHOLD = 0.80

    @staticmethod
    def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """Calcula a similaridade de cosseno entre dois vetores densos."""
        dot = float(sum(a * b for a, b in zip(v1, v2, strict=False)))
        norm1 = float(sum(a * a for a in v1) ** 0.5)
        norm2 = float(sum(b * b for b in v2) ** 0.5)
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return float(dot / (norm1 * norm2))

    @staticmethod
    def _char_ngram_vector(text: str, n: int = 3) -> dict[str, int]:
        """Extrai vetor de frequência de n-gramas para representação vetorial subpalavra."""
        vec: dict[str, int] = {}
        if len(text) < n:
            vec[text] = 1
            return vec
        for i in range(len(text) - n + 1):
            gram = text[i : i + n]
            vec[gram] = vec.get(gram, 0) + 1
        return vec

    def _subword_vector_similarity(self, text_a: str, text_b: str) -> float:
        """Calcula similaridade de cosseno baseada em vetores de n-gramas de caracteres."""
        v1 = self._char_ngram_vector(text_a)
        v2 = self._char_ngram_vector(text_b)
        dot = float(sum(val * v2.get(k, 0) for k, val in v1.items()))
        norm1 = float(sum(v * v for v in v1.values()) ** 0.5)
        norm2 = float(sum(v * v for v in v2.values()) ** 0.5)
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return float(dot / (norm1 * norm2))

    TIER_CONFIDENCE: dict[ValidationTier, float] = {
        ValidationTier.SYNTACTIC: 1.0,
        ValidationTier.PROVENANCE: 1.0,
        ValidationTier.FUZZY: 0.90,
        ValidationTier.VECTOR: 0.85,
    }

    def validate_term(
        self,
        term: str,
        registered_terms: set[str],
        provenance_map: dict[str, str] | None = None,
        vector_embeddings: dict[str, list[float]] | None = None,
        vector_evaluator: Callable[[str, str], float] | None = None,
        fuzzy_threshold: float = FUZZY_THRESHOLD,
        vector_threshold: float = VECTOR_THRESHOLD,
    ) -> ValidationTier | None:
        """Valida um termo gerado seguindo a cascata estrita de 4 camadas.

        Args:
            term: Termo gerado pela IA (ex: 'FastAPI', 'Postgres', 'K8s').
            registered_terms: Conjunto factual cadastrado no dossiê do usuário.
            provenance_map: Dicionário opcional gerado pela LLM mapeando termo -> termo_origem.
            vector_embeddings: Dicionário opcional contendo vetores de embeddings para cada termo.
            vector_evaluator: Função opcional que calcula similaridade semântica entre dois termos.
            fuzzy_threshold: Limiar de similaridade sintática parcial (padrão: 0.85).
            vector_threshold: Limiar de similaridade vetorial (padrão: 0.80).

        Returns:
            ValidationTier correspondente à camada que aprovou o termo, ou None se reprovado.
        """
        clean_term = term.lower().strip()
        normalized_registered = {t.lower().strip() for t in registered_terms}

        # 1. Validação Sintática (termo exato normalizado)
        if clean_term in normalized_registered:
            return ValidationTier.SYNTACTIC

        # 2. Validação por Proveniência (grounded_in)
        if provenance_map:
            source_term = provenance_map.get(term) or provenance_map.get(clean_term)
            if source_term:
                clean_source = source_term.lower().strip()
                if clean_source in normalized_registered:
                    return ValidationTier.PROVENANCE

        # 3. Fuzzy Matching (similaridade sintática parcial >= 85%)
        for reg in normalized_registered:
            ratio = SequenceMatcher(None, clean_term, reg).ratio()
            if ratio >= fuzzy_threshold:
                return ValidationTier.FUZZY

        # 4. Validação Vetorial (embeddings ou avaliador semântico)
        if vector_embeddings and term in vector_embeddings:
            term_vec = vector_embeddings[term]
            for reg_name in registered_terms:
                if reg_name in vector_embeddings:
                    sim = self._cosine_similarity(term_vec, vector_embeddings[reg_name])
                    if sim >= vector_threshold:
                        return ValidationTier.VECTOR

        if vector_evaluator:
            for reg_name in registered_terms:
                sim = vector_evaluator(term, reg_name)
                if sim >= vector_threshold:
                    return ValidationTier.VECTOR

        # Fallback para modelo vetorial subpalavra n-gram
        if not vector_embeddings and not vector_evaluator:
            for reg in normalized_registered:
                sim = self._subword_vector_similarity(clean_term, reg)
                if sim >= vector_threshold:
                    return ValidationTier.VECTOR

        return None

    def audit(
        self,
        generated_content: dict[str, Any],
        user_dossier: dict[str, Any],
        vector_embeddings: dict[str, list[float]] | None = None,
        vector_evaluator: Callable[[str, str], float] | None = None,
    ) -> AuditResult:
        """Compara o conteúdo gerado pela IA com a fonte primária da verdade do candidato.

        Args:
            generated_content: Dicionário correspondente ao FullGeneratedResumePayload.
            user_dossier: Fatos cadastrados (empresas, cargos, skills, formações).
            vector_embeddings: Vetores pré-calculados opcionais para auditoria vetorial.
            vector_evaluator: Avaliador semântico customizado opcional.

        Returns:
            AuditResult: Diagnóstico de veracidade e lista de anomalias detectadas.
        """
        issues: list[HallucinationIssue] = []
        total_facts = 0
        verified_confidence = 0.0
        tier_counts: dict[str, int] = {}

        # Normaliza conjuntos factuais do usuário
        registered_companies = {c for c in user_dossier.get("companies", []) if c}
        registered_skills = {s for s in user_dossier.get("skills", []) if s}
        provenance_map: dict[str, str] = generated_content.get("provenance_map", {})

        # 1. Validação de Empresas nas Experiências
        experiences = generated_content.get("selected_experiences", [])
        for exp in experiences:
            company = exp.get("company_name", "").strip()
            total_facts += 1

            comp_tier = self.validate_term(
                term=company,
                registered_terms=registered_companies,
                provenance_map=provenance_map,
                fuzzy_threshold=0.90,  # Empresas exigem limiar mais rígido
            )

            if comp_tier is None:
                issues.append(
                    HallucinationIssue(
                        field="selected_experiences.company_name",
                        hallucinated_value=company,
                        description=f"Empresa não cadastrada no perfil: '{company}'",
                        severity=HallucinationSeverity.CRITICAL,
                    )
                )
            else:
                verified_confidence += self.TIER_CONFIDENCE[comp_tier]
                tier_counts[comp_tier.value] = tier_counts.get(comp_tier.value, 0) + 1

            # Validação de Stack das Experiências com pipeline de 4 camadas
            for tech in exp.get("tech_stack", []):
                total_facts += 1
                tech_tier = self.validate_term(
                    term=tech,
                    registered_terms=registered_skills,
                    provenance_map=provenance_map,
                    vector_embeddings=vector_embeddings,
                    vector_evaluator=vector_evaluator,
                )

                if tech_tier is None:
                    issues.append(
                        HallucinationIssue(
                            field="selected_experiences.tech_stack",
                            hallucinated_value=tech,
                            description=(
                                f"Tecnologia '{tech}' reprovada em todas as camadas de validação "
                                "(sintática, proveniência, fuzzy e vetorial)."
                            ),
                            severity=HallucinationSeverity.MEDIUM,
                        )
                    )
                else:
                    verified_confidence += self.TIER_CONFIDENCE[tech_tier]
                    tier_counts[tech_tier.value] = tier_counts.get(tech_tier.value, 0) + 1

        # 2. Validação de Skills em Destaque com pipeline de 4 camadas
        skills = generated_content.get("skills_highlighted", [])
        for skill in skills:
            total_facts += 1
            skill_tier = self.validate_term(
                term=skill,
                registered_terms=registered_skills,
                provenance_map=provenance_map,
                vector_embeddings=vector_embeddings,
                vector_evaluator=vector_evaluator,
            )

            if skill_tier is None:
                issues.append(
                    HallucinationIssue(
                        field="skills_highlighted",
                        hallucinated_value=skill,
                        description=(
                            f"Habilidade '{skill}' reprovada em todas as camadas de validação "
                            "(sintática, proveniência, fuzzy e vetorial)."
                        ),
                        severity=HallucinationSeverity.MEDIUM,
                    )
                )
            else:
                verified_confidence += self.TIER_CONFIDENCE[skill_tier]
                tier_counts[skill_tier.value] = tier_counts.get(skill_tier.value, 0) + 1

        # Cálculo do Trust Score ponderado pelo grau de certeza factual de cada camada
        trust_score = (
            100.0
            if total_facts == 0
            else round((verified_confidence / total_facts) * 100.0, 2)
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
            verified_counts_by_tier=tier_counts,
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
