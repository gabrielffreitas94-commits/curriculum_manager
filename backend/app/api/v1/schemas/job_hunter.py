"""Schemas Pydantic v2 para o agente autônomo Job Hunter.

Define os modelos de configuração de metas (Goal Config), resultados
individuais de triagem de vagas e o payload consolidado de resposta da execução.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobHunterGoalConfig(BaseModel):
    """Configuração e critérios de busca/avaliação de vagas do Job Hunter."""

    model_config = ConfigDict(extra="ignore")

    source_urls: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Lista de URLs de vagas de emprego a serem analisadas.",
    )
    target_roles: list[str] = Field(
        default_factory=list,
        description="Cargos e títulos de interesse prioritário do candidato.",
    )
    min_match_score: float = Field(
        default=60.0,
        ge=0.0,
        le=100.0,
        description="Nota mínima percentual de aderência (match) para pré-candidatura.",
    )
    allowed_work_models: list[Literal["remote", "hybrid", "on-site"]] = Field(
        default=["remote", "hybrid", "on-site"],
        description="Modelos de trabalho aceitos pelo candidato.",
    )
    excluded_companies: list[str] = Field(
        default_factory=list,
        description="Empresas descartadas sumariamente (lista de bloqueio).",
    )
    auto_pre_apply: bool = Field(
        default=True,
        description="Se True, cria automaticamente o registro de candidatura no ATS Core.",
    )


class JobHunterItemResult(BaseModel):
    """Resultado da triagem e tomada de decisão de uma oportunidade individual."""

    model_config = ConfigDict(from_attributes=True)

    source_url: str
    company_name: str | None = None
    job_title: str | None = None
    work_model: str | None = None
    match_percentage: float = 0.0
    decision: Literal[
        "pre_applied",
        "approved_manual",
        "rejected_low_match",
        "rejected_criteria_mismatch",
        "skipped_duplicate",
        "failed_source",
    ]
    reason: str
    mandatory_requirements: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    application_id: uuid.UUID | None = None
    error_code: str | None = None


class JobHunterRunResponse(BaseModel):
    """Resposta consolidada da execução do agente Job Hunter."""

    model_config = ConfigDict(from_attributes=True)

    total_sources: int
    processed_count: int
    pre_applied_count: int
    rejected_count: int
    failed_count: int
    skipped_duplicate_count: int
    results: list[JobHunterItemResult] = Field(default_factory=list)
