"""Schemas Pydantic para gestão do ATS Core e ciclo de vida de candidaturas.

Define modelos estritos para operações CRUD de candidaturas, etapas seletivas,
contatos de recrutadores, notas cronológicas e métricas agregadas de conversão.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ApplicationStageCreate(BaseModel):
    """Payload para criação de uma etapa no processo seletivo da vaga.

    Attributes:
        stage_name: Nome descritivo da etapa (ex: 'Triagem com RH', 'Live Coding').
        order_index: Ordem sequencial da etapa no funil da oportunidade.
        status: Estado atual da etapa ('pending', 'scheduled', 'completed', 'skipped').
        scheduled_at: Data e hora programada para a entrevista ou teste (UTC).
        completed_at: Momento da finalização da etapa (UTC).
        feedback_notes: Anotações ou feedback recebido dos avaliadores.
    """

    stage_name: str = Field(..., min_length=1, max_length=100)
    order_index: int = Field(default=0, ge=0)
    status: str = Field(default="pending", max_length=30)
    scheduled_at: datetime | None = None
    completed_at: datetime | None = None
    feedback_notes: str | None = None


class ApplicationStageUpdate(BaseModel):
    """Payload para atualização de uma etapa de avaliação."""

    stage_name: str | None = Field(default=None, min_length=1, max_length=100)
    order_index: int | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, max_length=30)
    scheduled_at: datetime | None = None
    completed_at: datetime | None = None
    feedback_notes: str | None = None


class ApplicationStageResponse(BaseModel):
    """Representação serializada de uma etapa seletiva."""

    id: uuid.UUID
    application_id: uuid.UUID
    stage_name: str
    status: str
    scheduled_at: datetime | None = None
    completed_at: datetime | None = None
    feedback_notes: str | None = None
    order_index: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationContactCreate(BaseModel):
    """Payload para inclusão de contato profissional de recrutamento."""

    name: str | None = None
    full_name: str | None = None
    role: str | None = None
    role_type: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    context_notes: str | None = None


class ApplicationContactResponse(BaseModel):
    """Representação serializada de contato de recrutamento."""

    id: uuid.UUID
    application_id: uuid.UUID
    name: str
    full_name: str
    role: str
    role_type: str
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    context_notes: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationNoteCreate(BaseModel):
    """Payload para inclusão de anotação na vaga."""

    content: str = Field(..., min_length=1)
    note_type: str = Field(default="general", max_length=30)


class ApplicationNoteResponse(BaseModel):
    """Representação serializada de nota de candidatura."""

    id: uuid.UUID
    application_id: uuid.UUID
    content: str
    note_type: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationCreate(BaseModel):
    """Payload para criação de uma candidatura no ATS."""

    company_name: str = Field(..., min_length=1, max_length=150)
    job_title: str = Field(..., min_length=1, max_length=120)
    job_description: str = Field(default="", max_length=50000)
    job_url: str | None = None
    work_model: str = Field(default="remote", max_length=20)
    salary_range: str | None = None
    location: str | None = None
    status: str = Field(default="applied", max_length=30)
    next_follow_up_date: date | None = None
    reminder_active: bool = True


class ApplicationUpdate(BaseModel):
    """Payload para atualização parcial de candidatura."""

    company_name: str | None = Field(default=None, min_length=1, max_length=150)
    job_title: str | None = Field(default=None, min_length=1, max_length=120)
    job_description: str | None = Field(default=None, max_length=50000)
    job_url: str | None = None
    work_model: str | None = Field(default=None, max_length=20)
    salary_range: str | None = None
    location: str | None = None
    status: str | None = Field(default=None, max_length=30)
    next_follow_up_date: date | None = None
    reminder_active: bool | None = None


class ApplicationListItemResponse(BaseModel):
    """Representação resumida da candidatura para listagem e kanban."""

    id: uuid.UUID
    company_name: str
    job_title: str
    status: str
    work_model: str
    applied_at: date
    last_activity_at: datetime
    needs_follow_up: bool = False
    location: str | None = None
    salary_range: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ApplicationDetailResponse(BaseModel):
    """Representação detalhada da candidatura incluindo relações agregadas."""

    id: uuid.UUID
    company_name: str
    job_title: str
    job_description: str
    job_url: str | None = None
    status: str
    work_model: str
    salary_range: str | None = None
    location: str | None = None
    applied_at: date
    last_activity_at: datetime
    next_follow_up_date: date | None = None
    reminder_active: bool
    needs_follow_up: bool = False
    stages: list[ApplicationStageResponse] = Field(default_factory=list)
    contacts: list[ApplicationContactResponse] = Field(default_factory=list)
    notes: list[ApplicationNoteResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ApplicationAnalyticsMetrics(BaseModel):
    """Métricas consolidadas de desempenho do candidato no ATS."""

    total_applications: int
    status_distribution: dict[str, int]
    stale_applications_count: int
    interview_conversion_rate: float
    offer_conversion_rate: float
    average_match_score: float
