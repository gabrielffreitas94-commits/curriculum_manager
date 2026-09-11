"""Schemas Pydantic v2 para o Dossiê e Repositório Profissional do usuário."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Experiências ---
class ExperienceCreateRequest(BaseModel):
    """Payload de criação de uma nova experiência profissional."""

    company_name: str = Field(..., max_length=150)
    position_title: str = Field(..., max_length=120)
    location: str | None = Field(default=None, max_length=100)
    work_model: str = Field(default="remote", max_length=20)
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description: str
    bullet_points: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    quantifiable_results: list[str] = Field(default_factory=list)
    sort_order: int = 0


class ExperienceUpdateRequest(BaseModel):
    """Payload de atualização parcial de uma experiência profissional."""

    company_name: str | None = None
    position_title: str | None = None
    location: str | None = None
    work_model: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None
    description: str | None = None
    bullet_points: list[str] | None = None
    tech_stack: list[str] | None = None
    quantifiable_results: list[str] | None = None
    sort_order: int | None = None


class ExperienceResponse(BaseModel):
    """Resposta serializada de experiência profissional."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    company_name: str
    position_title: str
    location: str | None
    work_model: str
    start_date: date
    end_date: date | None
    is_current: bool
    description: str
    bullet_points: list[str]
    tech_stack: list[str]
    quantifiable_results: list[str]
    sort_order: int
    created_at: datetime
    updated_at: datetime


# --- Formação Acadêmica ---
class EducationCreateRequest(BaseModel):
    """Payload de criação de formação acadêmica."""

    institution_name: str = Field(..., max_length=150)
    degree: str = Field(..., max_length=100)
    field_of_study: str = Field(..., max_length=150)
    start_date: date
    end_date: date | None = None
    is_current: bool = False
    description: str | None = None
    sort_order: int = 0


class EducationUpdateRequest(BaseModel):
    """Payload de atualização parcial de formação acadêmica."""

    institution_name: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None
    description: str | None = None
    sort_order: int | None = None


class EducationResponse(BaseModel):
    """Resposta serializada de formação acadêmica."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    institution_name: str
    degree: str
    field_of_study: str
    start_date: date
    end_date: date | None
    is_current: bool
    description: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


# --- Certificações ---
class CertificationCreateRequest(BaseModel):
    """Payload de criação de certificação técnica."""

    name: str = Field(..., max_length=150)
    issuing_organization: str = Field(..., max_length=150)
    issue_date: date
    expiration_date: date | None = None
    credential_id: str | None = Field(default=None, max_length=100)
    credential_url: str | None = Field(default=None, max_length=255)
    sort_order: int = 0


class CertificationUpdateRequest(BaseModel):
    """Payload de atualização parcial de certificação."""

    name: str | None = None
    issuing_organization: str | None = None
    issue_date: date | None = None
    expiration_date: date | None = None
    credential_id: str | None = None
    credential_url: str | None = None
    sort_order: int | None = None


class CertificationResponse(BaseModel):
    """Resposta serializada de certificação técnica."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    issuing_organization: str
    issue_date: date
    expiration_date: date | None
    credential_id: str | None
    credential_url: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


# --- Projetos ---
class ProjectCreateRequest(BaseModel):
    """Payload de criação de projeto ou portfólio."""

    title: str = Field(..., max_length=150)
    description: str
    role: str | None = Field(default=None, max_length=100)
    technologies: list[str] = Field(default_factory=list)
    repository_url: str | None = Field(default=None, max_length=255)
    live_url: str | None = Field(default=None, max_length=255)
    start_date: date | None = None
    end_date: date | None = None
    sort_order: int = 0


class ProjectUpdateRequest(BaseModel):
    """Payload de atualização parcial de projeto."""

    title: str | None = None
    description: str | None = None
    role: str | None = None
    technologies: list[str] | None = None
    repository_url: str | None = None
    live_url: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    sort_order: int | None = None


class ProjectResponse(BaseModel):
    """Resposta serializada de projeto."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: str
    role: str | None
    technologies: list[str]
    repository_url: str | None
    live_url: str | None
    start_date: date | None
    end_date: date | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


# --- Competências (Skills) ---
class SkillCreateRequest(BaseModel):
    """Payload de criação de competência técnica ou comportamental."""

    name: str = Field(..., max_length=100)
    category: str = Field(default="backend", max_length=50)
    proficiency_level: str = Field(default="intermediate", max_length=30)
    years_of_experience: int = Field(default=1, ge=0)
    is_featured: bool = False


class SkillUpdateRequest(BaseModel):
    """Payload de atualização parcial de competência."""

    name: str | None = None
    category: str | None = None
    proficiency_level: str | None = None
    years_of_experience: int | None = None
    is_featured: bool | None = None


class SkillResponse(BaseModel):
    """Resposta serializada de competência."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    category: str
    proficiency_level: str
    years_of_experience: int
    is_featured: bool
    created_at: datetime
    updated_at: datetime


# --- Idiomas ---
class LanguageCreateRequest(BaseModel):
    """Payload de criação de idioma falado."""

    language_name: str = Field(..., max_length=50)
    proficiency_level: str = Field(..., max_length=30)


class LanguageUpdateRequest(BaseModel):
    """Payload de atualização de idioma."""

    language_name: str | None = None
    proficiency_level: str | None = None


class LanguageResponse(BaseModel):
    """Resposta serializada de idioma."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    language_name: str
    proficiency_level: str
    created_at: datetime
    updated_at: datetime


# --- Dossiê Agregado Completo ---
class FullDossierResponse(BaseModel):
    """Resposta agregada contendo todo o dossiê profissional do usuário."""

    experiences: list[ExperienceResponse]
    educations: list[EducationResponse]
    certifications: list[CertificationResponse]
    projects: list[ProjectResponse]
    skills: list[SkillResponse]
    languages: list[LanguageResponse]
