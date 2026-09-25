"""Porta abstrata para o serviço de extração estruturada de currículos (Hexagonal Architecture).

Define os contratos e DTOs puros de transferência de dados para parsing
de documentos profissionais (PDF/DOCX) com garantia de zero alucinação.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field


class ResumeParserError(Exception):
    """Exceção base para erros durante o processo de parsing de currículo."""


class ParsingExecutionError(ResumeParserError):
    """Lançada quando a engine de IA ou o parser falha ao processar o documento."""


class CorruptedFileError(ResumeParserError):
    """Lançada quando o arquivo não pôde ser lido estruturalmente."""


class ParsedPersonalDataDTO(BaseModel):
    """Dados cadastrais e links de contato extraídos do currículo."""

    model_config = ConfigDict(extra="ignore")

    full_name: str | None = None
    headline: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None


class ParsedExperienceDTO(BaseModel):
    """Experiência profissional extraída fielmente do currículo."""

    model_config = ConfigDict(extra="ignore")

    company_name: str = Field(..., max_length=150)
    position_title: str = Field(..., max_length=120)
    location: str | None = None
    work_model: str = Field(default="remote")
    start_date: str = Field(..., description="Data em formato YYYY-MM-DD ou YYYY-MM")
    end_date: str | None = None
    is_current: bool = False
    description: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    quantifiable_results: list[str] = Field(default_factory=list)


class ParsedEducationDTO(BaseModel):
    """Formação acadêmica extraída do currículo."""

    model_config = ConfigDict(extra="ignore")

    institution_name: str = Field(..., max_length=150)
    degree: str = Field(..., max_length=100)
    field_of_study: str = Field(..., max_length=150)
    start_date: str = Field(..., description="Data em formato YYYY-MM-DD ou YYYY-MM")
    end_date: str | None = None
    is_current: bool = False
    description: str | None = None


class ParsedSkillDTO(BaseModel):
    """Competência técnica ou comportamental extraída do currículo."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., max_length=100)
    category: str = Field(default="backend", max_length=50)
    proficiency_level: str = Field(default="intermediate", max_length=30)
    years_of_experience: int = Field(default=1, ge=0)


class ParsedLanguageDTO(BaseModel):
    """Idioma falado e nível de proficiência extraído do currículo."""

    model_config = ConfigDict(extra="ignore")

    language_name: str = Field(..., max_length=50)
    proficiency_level: str = Field(default="professional", max_length=30)


class ParsedCertificationDTO(BaseModel):
    """Certificação profissional extraída do currículo."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., max_length=150)
    issuing_organization: str = Field(..., max_length=150)
    issue_date: str = Field(..., description="Data em formato YYYY-MM-DD ou YYYY-MM")
    expiration_date: str | None = None
    credential_id: str | None = None
    credential_url: str | None = None


class ParsedProjectDTO(BaseModel):
    """Projeto ou iniciativa de destaque extraída do currículo."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., max_length=150)
    description: str = ""
    role: str | None = None
    technologies: list[str] = Field(default_factory=list)
    repository_url: str | None = None
    live_url: str | None = None


class ParsedProfileDTO(BaseModel):
    """Dossiê agregado extraído na íntegra a partir do documento original."""

    model_config = ConfigDict(extra="ignore")

    personal_data: ParsedPersonalDataDTO = Field(default_factory=ParsedPersonalDataDTO)
    experiences: list[ParsedExperienceDTO] = Field(default_factory=list)
    educations: list[ParsedEducationDTO] = Field(default_factory=list)
    skills: list[ParsedSkillDTO] = Field(default_factory=list)
    languages: list[ParsedLanguageDTO] = Field(default_factory=list)
    certifications: list[ParsedCertificationDTO] = Field(default_factory=list)
    projects: list[ParsedProjectDTO] = Field(default_factory=list)


class ResumeParserPort(ABC):
    """Contrato abstrato para adaptadores de extração de currículos."""

    @abstractmethod
    async def parse_resume(
        self,
        file_bytes: bytes,
        mime_type: str,
        filename: str,
    ) -> ParsedProfileDTO:
        """Processa o binário de um documento de currículo e extrai os dados estruturados.

        Args:
            file_bytes: Conteúdo binário bruto validado do arquivo.
            mime_type: MIME type correspondente ('application/pdf' ou 'application/vnd...').
            filename: Nome original do arquivo.

        Returns:
            ParsedProfileDTO: Estrutura completa dos dados extraídos com fidelidade factual.

        Raises:
            ResumeParserError: Se o parsing falhar ou for recusado.
        """
