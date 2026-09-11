"""Motor de correspondência semântica e cálculo de score de aderência (VectorMatchEngine).

Avalia o grau de atendimento de requisitos de vagas contra o dossiê factual
do candidato, identificando competências atendidas, lacunas parciais/ausentes
e palavras-chave ATS recomendadas, em estrita conformidade anti-alucinação.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.ports.ai_port import JobAnalysisResult


@dataclass
class MatchAnalysisItem:
    """Classificação individual de aderência para um requisito da vaga.

    Attributes:
        requirement: Texto do requisito (ex: 'Python', 'Arquitetura de Microsserviços').
        status: Estado de atendimento ('matched', 'partial', 'missing').
        evidence: Justificativa factual ou fonte no dossiê onde o item foi evidenciado.
        similarity_score: Grau numérico de confiança (0.0 a 1.0).
    """

    requirement: str
    status: str
    evidence: str
    similarity_score: float = 0.0


@dataclass
class MatchEvaluationResult:
    """Resultado consolidado da avaliação de fit do candidato contra a vaga.

    Attributes:
        match_percentage: Pontuação global de aderência quantificada (0.0 a 100.0).
        mandatory_matches: Matriz detalhada dos requisitos obrigatórios.
        desirable_matches: Matriz detalhada dos requisitos desejáveis.
        missing_mandatory: Lista de termos obrigatórios não identificados no perfil.
        missing_desirable: Lista de termos desejáveis não identificados no perfil.
        suggested_keywords: Palavras-chave ATS ausentes no perfil do candidato.
    """

    match_percentage: float
    mandatory_matches: list[MatchAnalysisItem] = field(default_factory=list)
    desirable_matches: list[MatchAnalysisItem] = field(default_factory=list)
    missing_mandatory: list[str] = field(default_factory=list)
    missing_desirable: list[str] = field(default_factory=list)
    suggested_keywords: list[str] = field(default_factory=list)


class VectorMatchEngine:
    """Algoritmo de cálculo de similaridade e correspondência factual de qualificações."""

    def evaluate_match(
        self,
        dossier: dict[str, Any],
        job_analysis: JobAnalysisResult,
    ) -> MatchEvaluationResult:
        """Calcula a aderência do candidato contra os requisitos analisados da oportunidade.

        Args:
            dossier: Dicionário com skills, experiências, formações e certificações reais.
            job_analysis: Requisitos mandatórios, desejáveis e palavras-chave extraídos.

        Returns:
            MatchEvaluationResult com score ponderado e matriz detalhada de fit.
        """
        candidate_corpus = self._build_candidate_corpus(dossier)

        # Avaliação de Requisitos Mandatórios
        mandatory_matches: list[MatchAnalysisItem] = []
        missing_mandatory: list[str] = []
        mandatory_score_sum = 0.0

        for req in job_analysis.mandatory_requirements:
            item = self._match_requirement(req, candidate_corpus)
            mandatory_matches.append(item)
            mandatory_score_sum += item.similarity_score
            if item.status == "missing":
                missing_mandatory.append(req)

        # Avaliação de Requisitos Desejáveis
        desirable_matches: list[MatchAnalysisItem] = []
        missing_desirable: list[str] = []
        desirable_score_sum = 0.0

        for req in job_analysis.desirable_requirements:
            item = self._match_requirement(req, candidate_corpus)
            desirable_matches.append(item)
            desirable_score_sum += item.similarity_score
            if item.status == "missing":
                missing_desirable.append(req)

        # Cálculo do Score Ponderado: 70% mandatórios, 30% desejáveis
        num_mand = len(job_analysis.mandatory_requirements)
        num_des = len(job_analysis.desirable_requirements)

        mand_ratio = (mandatory_score_sum / num_mand) if num_mand > 0 else 1.0
        des_ratio = (desirable_score_sum / num_des) if num_des > 0 else 1.0

        if num_mand > 0 and num_des > 0:
            final_score = (mand_ratio * 0.70) + (des_ratio * 0.30)
        elif num_mand > 0:
            final_score = mand_ratio
        else:
            final_score = des_ratio

        match_percentage = round(min(1.0, max(0.0, final_score)) * 100.0, 2)

        # Sugestões de palavras-chave ATS não encontradas
        suggested_kw: list[str] = []
        for kw in job_analysis.keywords:
            if not self._token_exists_in_corpus(kw, candidate_corpus):
                suggested_kw.append(kw)

        return MatchEvaluationResult(
            match_percentage=match_percentage,
            mandatory_matches=mandatory_matches,
            desirable_matches=desirable_matches,
            missing_mandatory=missing_mandatory,
            missing_desirable=missing_desirable,
            suggested_keywords=suggested_kw,
        )

    def _build_candidate_corpus(self, dossier: dict[str, Any]) -> dict[str, list[str]]:
        """Extrai e categoriza o universo textual do candidato para busca semântica.

        Args:
            dossier: Dossiê com entidades cadastradas.

        Returns:
            Dicionário com conjuntos textuais normalizados.
        """
        corpus: dict[str, list[str]] = {
            "skills": [],
            "companies": [],
            "experiences": [],
            "certifications": [],
        }

        # Skills
        for sk in dossier.get("skills", []):
            name = sk if isinstance(sk, str) else sk.get("name", "")
            if name:
                corpus["skills"].append(name.strip())

        # Experiências
        for exp in dossier.get("experiences", []):
            comp = exp.get("company_name", "")
            role = exp.get("position_title", "")
            stack_str = " ".join(exp.get("tech_stack", []))
            bullets_str = " ".join(exp.get("bullet_points", []))
            full_exp = f"{comp} {role} {stack_str} {bullets_str}"
            corpus["experiences"].append(full_exp.strip())
            corpus["skills"].extend(exp.get("tech_stack", []))

        # Certificações
        for cert in dossier.get("certifications", []):
            name = cert if isinstance(cert, str) else cert.get("name", "")
            if name:
                corpus["certifications"].append(name.strip())

        return corpus

    def _match_requirement(
        self,
        requirement: str,
        corpus: dict[str, list[str]],
    ) -> MatchAnalysisItem:
        """Verifica a presença e relevância de um requisito no perfil do candidato.

        Args:
            requirement: Termo da vaga.
            corpus: Textos normalizados do perfil.

        Returns:
            MatchAnalysisItem correspondente.
        """
        req_clean = requirement.strip().lower()

        # 1. Correspondência direta em Skills
        for sk in corpus["skills"]:
            if req_clean == sk.lower():
                return MatchAnalysisItem(
                    requirement=requirement,
                    status="matched",
                    evidence=f"Habilidade cadastrada no perfil: {sk}",
                    similarity_score=1.0,
                )
            if req_clean in sk.lower() or sk.lower() in req_clean:
                return MatchAnalysisItem(
                    requirement=requirement,
                    status="matched",
                    evidence=f"Habilidade relacionada no perfil: {sk}",
                    similarity_score=0.9,
                )

        # 2. Correspondência em Experiências
        for exp in corpus["experiences"]:
            if re.search(rf"\b{re.escape(req_clean)}\b", exp.lower()):
                return MatchAnalysisItem(
                    requirement=requirement,
                    status="matched",
                    evidence="Identificado no histórico de atuação profissional.",
                    similarity_score=1.0,
                )

        # 3. Correspondência em Certificações
        for cert in corpus["certifications"]:
            if req_clean in cert.lower():
                return MatchAnalysisItem(
                    requirement=requirement,
                    status="matched",
                    evidence=f"Comprovado por certificação: {cert}",
                    similarity_score=1.0,
                )

        # 4. Caso não encontrado
        return MatchAnalysisItem(
            requirement=requirement,
            status="missing",
            evidence="Requisito não identificado no dossiê de experiências.",
            similarity_score=0.0,
        )

    def _token_exists_in_corpus(self, token: str, corpus: dict[str, list[str]]) -> bool:
        """Verifica existência de um token ou termo no universo do candidato.

        Args:
            token: Palavra-chave a verificar.
            corpus: Dicionário do candidato.

        Returns:
            True se presente, False se ausente.
        """
        tok = token.strip().lower()
        for sk in corpus["skills"]:
            if tok in sk.lower() or sk.lower() in tok:
                return True
        for cert in corpus["certifications"]:
            if tok in cert.lower():
                return True
        return any(tok in exp.lower() for exp in corpus["experiences"])
