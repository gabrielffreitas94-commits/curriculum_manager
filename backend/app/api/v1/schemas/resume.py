"""Schemas Pydantic para análise de vagas e geração inteligente de currículos."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class JobAnalyzeRequest(BaseModel):
    """Payload para extração semântica de requisitos da vaga.

    Attributes:
        job_description: Texto completo do anúncio da oportunidade.
    """

    job_description: str = Field(..., min_length=20, max_length=50000)


class ResumeGenerateRequest(BaseModel):
    """Payload para acionamento do pipeline de geração inteligente de currículo.

    Attributes:
        job_description: Texto integral da descrição da vaga.
        prompt_skill_slug: Slug da persona de prompt ('tech-startup', 'corporate', etc.).
        language: Idioma de redação do currículo ('pt-BR', 'en-US', etc.).
        application_id: UUID de candidatura já existente (opcional).
        create_application: Se True, cria automaticamente o registro no ATS
            se application_id for None.
        company_name: Nome da empresa contratante (necessário se create_application for True).
        job_title: Título da vaga pretendida.
        job_url: Link da postagem original da vaga.
    """

    job_description: str = Field(..., min_length=20, max_length=50000)
    prompt_skill_slug: str = Field(default="tech-startup", max_length=50)
    language: str = Field(default="pt-BR", max_length=10)
    application_id: uuid.UUID | None = None
    create_application: bool = True
    company_name: str | None = Field(default=None, max_length=150)
    job_title: str | None = Field(default=None, max_length=120)
    job_url: str | None = Field(default=None, max_length=500)


class ResumeGenerateResponse(BaseModel):
    """Resposta consolidada com os identificadores e dados do currículo gerado.

    Attributes:
        resume_id: Identificador único do registro de GeneratedResume.
        application_id: Identificador da candidatura vinculada no ATS.
        version_number: Número da versão sequencial incrementada para a mesma candidatura.
        match_percentage: Pontuação global de aderência quantificada (0.0 a 100.0).
        match_analysis: Detalhamento dos requisitos atendidos, parciais e ausentes.
        structured_content: Conteúdo integral estruturado do currículo para exibição e edição.
    """

    resume_id: uuid.UUID
    application_id: uuid.UUID
    version_number: int
    match_percentage: float
    match_analysis: dict[str, Any]
    structured_content: dict[str, Any]


class MatchPreviewRequest(BaseModel):
    """Payload para pré-visualização de match contra anúncio de vaga."""

    job_description: str = Field(..., min_length=20, max_length=50000)


class MatchAnalysisItemSchema(BaseModel):
    """Item individual da matriz de aderência de requisitos."""

    requirement: str
    status: str
    evidence: str
    similarity_score: float = 0.0


class MatchPreviewResponse(BaseModel):
    """Resposta da pré-visualização rápida de aderência e fit do candidato."""

    match_percentage: float
    mandatory_matches: list[MatchAnalysisItemSchema] = Field(default_factory=list)
    desirable_matches: list[MatchAnalysisItemSchema] = Field(default_factory=list)
    missing_mandatory: list[str] = Field(default_factory=list)
    missing_desirable: list[str] = Field(default_factory=list)
    suggested_keywords: list[str] = Field(default_factory=list)
