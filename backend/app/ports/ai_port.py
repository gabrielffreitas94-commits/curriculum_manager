"""Porta abstrata para integração com modelos fundacionais de IA (Google Gemini).

Define as interfaces para decomposição semântica de oportunidades de emprego,
matching ponderado de competências e síntese estruturada de currículos.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class AIError(Exception):
    """Exceção base para falhas de comunicação ou processamento da IA."""

    pass


class MissingApiKeyError(AIError):
    """Lançada quando uma chamada ao Gemini é feita sem uma API Key configurada."""

    pass


class GenerationError(AIError):
    """Lançada quando a geração estruturada falha ou não respeita os contratos."""

    pass


class HallucinationDetectedError(AIError):
    """Lançada quando a auditoria algorítmica detecta dados forjados inaceitáveis."""

    pass


class JobAnalysisResult(BaseModel):
    """Resultado da análise semântica e extração de requisitos da vaga (Estágio 1).

    Attributes:
        job_title: Título identificado da oportunidade.
        seniority_level: Nível de senioridade detectado (ex: 'Senior', 'Pleno', 'Lead').
        mandatory_requirements: Lista de requisitos essenciais mandatórios.
        desirable_requirements: Lista de requisitos diferenciais desejáveis.
        keywords: Termos técnicos essenciais para aderência ATS.
    """

    job_title: str
    seniority_level: str
    mandatory_requirements: list[str] = Field(default_factory=list)
    desirable_requirements: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class FullGeneratedResumePayload(BaseModel):
    """JSON estruturado final do currículo gerado sob restrições estritas (Estágio 3).

    Attributes:
        header: Dados de cabeçalho do candidato formatados para a vaga.
        professional_summary: Resumo narrativo persuasivo e 100% verídico.
        selected_experiences: Experiências re-ranqueadas e estilizadas com verbos de ação.
        skills_highlighted: Competências mais convergentes com a oportunidade.
        education: Formação acadêmica relevante.
        certifications: Certificações técnicas.
        projects: Projetos de destaque selecionados.
        languages: Idiomas e níveis de fluência declarados.
        match_analysis: Relatório de aderência aos requisitos mandatórios e desejáveis.
        match_percentage: Pontuação de aderência global calculada (0.0 a 100.0).
    """

    header: dict[str, Any]
    professional_summary: str
    selected_experiences: list[dict[str, Any]] = Field(default_factory=list)
    skills_highlighted: list[str] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    languages: list[dict[str, Any]] = Field(default_factory=list)
    match_analysis: dict[str, Any] = Field(default_factory=dict)
    match_percentage: float = 0.0
    provenance_map: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapeamento de proveniência indicando o termo factual do dossiê usado como base."
        ),
    )


class AIPort(ABC):
    """Interface abstrata para consumo de modelos LLM."""

    @abstractmethod
    async def analyze_job(self, job_description: str) -> JobAnalysisResult:
        """Extrai requisitos mandatórios, desejáveis e palavras-chave da vaga.

        Args:
            job_description: Texto completo do anúncio da oportunidade.

        Returns:
            JobAnalysisResult: Requisitos e termos ATS extraídos de forma estruturada.

        Raises:
            MissingApiKeyError: Se a chave do Gemini não for informada.
            AIError: Se o provedor de IA falhar na resposta.
        """
        pass

    @abstractmethod
    async def generate_resume(
        self,
        job_description: str,
        user_dossier: dict[str, Any],
        prompt_skill_instructions: str,
        language: str = "pt-BR",
    ) -> FullGeneratedResumePayload:
        """Gera um currículo adaptado via Structured Outputs respeitando os fatos do usuário.

        Args:
            job_description: Anúncio da vaga de emprego.
            user_dossier: Fatos cadastrados no banco relacional (Ground Truth).
            prompt_skill_instructions: Diretrizes do template de persona escolhido.
            language: Idioma de destino da redação ('pt-BR', 'en-US', etc.).

        Returns:
            FullGeneratedResumePayload: Currículo estruturado e análise de aderência.

        Raises:
            MissingApiKeyError: Se a API key do Gemini estiver ausente.
            GenerationError: Se a geração violar o schema estruturado.
        """
        pass
