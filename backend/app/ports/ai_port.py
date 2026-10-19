"""Porta abstrata para integração com modelos fundacionais de IA (Google Gemini).

Define as interfaces para decomposição semântica de oportunidades de emprego,
matching ponderado de competências e síntese estruturada de currículos.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


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


class ModelUnavailableError(AIError):
    """Lançada quando o modelo de IA solicitado está temporariamente indisponível ou sobrecarregado."""

    def __init__(self, message: str, model: str | None = None) -> None:
        super().__init__(message)
        self.model = model


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


class SubscriptableModel(BaseModel):
    """BaseModel com suporte transparente a indexação por chave ('obj[\"campo\"]' e 'obj.get(\"campo\")')."""

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class GeneratedResumeHeader(SubscriptableModel):
    """Dados de cabeçalho do candidato formatados para a vaga."""

    model_config = ConfigDict(extra="ignore")

    full_name: str | None = None
    target_title: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _handle_legacy_links(cls, data: Any) -> Any:
        if isinstance(data, dict) and "links" in data:
            links = data.get("links")
            if isinstance(links, dict):
                if not data.get("github_url") and "github" in links:
                    data["github_url"] = links["github"]
                if not data.get("linkedin_url") and "linkedin" in links:
                    data["linkedin_url"] = links["linkedin"]
                if not data.get("portfolio_url") and "portfolio" in links:
                    data["portfolio_url"] = links["portfolio"]
        return data

    @computed_field
    def links(self) -> dict[str, str]:
        res: dict[str, str] = {}
        if self.linkedin_url:
            res["linkedin"] = self.linkedin_url
        if self.github_url:
            res["github"] = self.github_url
        if self.portfolio_url:
            res["portfolio"] = self.portfolio_url
        return res


class GeneratedExperience(SubscriptableModel):
    """Experiência profissional adaptada e estilizada."""

    model_config = ConfigDict(extra="ignore")

    company_name: str = ""
    position_title: str = ""
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    location: str | None = None
    description: str | None = None
    bullet_points: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    quantifiable_results: list[str] = Field(default_factory=list)
    sort_order: int = 0

    @model_validator(mode="before")
    @classmethod
    def _handle_legacy_bullets(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "achievements" in data and not data.get("bullet_points"):
                data["bullet_points"] = data.get("achievements") or []
        return data

    @computed_field
    def achievements(self) -> list[str]:
        return self.bullet_points


class GeneratedEducation(SubscriptableModel):
    """Formação acadêmica selecionada."""

    model_config = ConfigDict(extra="ignore")

    institution_name: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    description: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_institution(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("institution_name") and data.get("institution"):
                data["institution_name"] = str(data["institution"])
        return data

    @computed_field
    def institution(self) -> str:
        return self.institution_name


class GeneratedCertification(SubscriptableModel):
    """Certificação técnica relevante."""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    issuing_organization: str | None = None
    issue_date: str | None = None
    expiration_date: str | None = None
    credential_id: str | None = None
    credential_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_issuer(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("issuing_organization") and data.get("issuer"):
                data["issuing_organization"] = str(data["issuer"])
        return data

    @computed_field
    def issuer(self) -> str | None:
        return self.issuing_organization


class GeneratedProject(SubscriptableModel):
    """Projeto ou iniciativa de destaque."""

    model_config = ConfigDict(extra="ignore")

    title: str = ""
    description: str | None = None
    role: str | None = None
    technologies: list[str] = Field(default_factory=list)
    bullet_points: list[str] = Field(default_factory=list)
    repository_url: str | None = None
    live_url: str | None = None
    sort_order: int = 0


class GeneratedLanguage(SubscriptableModel):
    """Idioma e proficiência declarados."""

    model_config = ConfigDict(extra="ignore")

    language_name: str = ""
    proficiency_level: str = "professional"

    @model_validator(mode="before")
    @classmethod
    def _normalize_lang(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("language_name") and data.get("language"):
                data["language_name"] = str(data["language"])
            if data.get("proficiency") and (
                not data.get("proficiency_level") or data.get("proficiency_level") == "professional"
            ):
                data["proficiency_level"] = str(data["proficiency"])
        return data

    @computed_field
    def language(self) -> str:
        return self.language_name

    @computed_field
    def proficiency(self) -> str:
        return self.proficiency_level


class MatchRequirementItem(SubscriptableModel):
    """Item de requisito avaliado na análise de aderência."""

    model_config = ConfigDict(extra="ignore")

    requirement: str = ""
    status: str = "matched"
    evidence: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_req(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"requirement": data, "status": "matched", "evidence": ""}
        return data


class GeneratedMatchAnalysis(SubscriptableModel):
    """Relatório estruturado de aderência aos requisitos da vaga."""

    model_config = ConfigDict(extra="ignore")

    mandatory_requirements: list[MatchRequirementItem] = Field(default_factory=list)
    desirable_requirements: list[MatchRequirementItem] = Field(default_factory=list)
    differentiating_factors: list[str] = Field(default_factory=list)
    summary: str = ""


class ProvenanceItem(SubscriptableModel):
    """Mapeamento de proveniência factual para auditoria anti-alucinação."""

    model_config = ConfigDict(extra="ignore")

    synthesized_term: str = Field(description="Termo usado no currículo")
    grounded_in_term: str = Field(description="Termo factual correspondente no dossiê")


class FullGeneratedResumePayload(SubscriptableModel):
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
        provenance_items: Lista de itens mapeando termos aos fatos reais do dossiê.
    """

    model_config = ConfigDict(extra="ignore")

    header: GeneratedResumeHeader
    professional_summary: str
    selected_experiences: list[GeneratedExperience] = Field(default_factory=list)
    skills_highlighted: list[str] = Field(default_factory=list)
    education: list[GeneratedEducation] = Field(default_factory=list)
    certifications: list[GeneratedCertification] = Field(default_factory=list)
    projects: list[GeneratedProject] = Field(default_factory=list)
    languages: list[GeneratedLanguage] = Field(default_factory=list)
    match_analysis: GeneratedMatchAnalysis = Field(default_factory=GeneratedMatchAnalysis)
    match_percentage: float = 0.0
    provenance_items: list[ProvenanceItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _handle_legacy_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "provenance_map" in data and not data.get("provenance_items"):
                pmap = data.pop("provenance_map", {})
                if isinstance(pmap, dict):
                    data["provenance_items"] = [
                        {"synthesized_term": k, "grounded_in_term": str(v)} for k, v in pmap.items()
                    ]
        return data

    @computed_field
    def provenance_map(self) -> dict[str, str]:
        return {item.synthesized_term: item.grounded_in_term for item in self.provenance_items}


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
        chat_history: list["ChatMessage"] | None = None,
        previous_resume: dict[str, Any] | None = None,
    ) -> FullGeneratedResumePayload:
        """Gera um currículo adaptado via Structured Outputs respeitando os fatos do usuário.

        Args:
            job_description: Anúncio da vaga de emprego.
            user_dossier: Fatos cadastrados no banco relacional (Ground Truth).
            prompt_skill_instructions: Diretrizes do template de persona escolhido.
            language: Idioma de destino da redação ('pt-BR', 'en-US', etc.).
            chat_history: Histórico opcional de alinhamento com o Copilot para regeração calibrada.
            previous_resume: Versão anterior opcional do currículo como rascunho base de evolução.

        Returns:
            FullGeneratedResumePayload: Currículo estruturado e análise de aderência.

        Raises:
            MissingApiKeyError: Se a API key do Gemini estiver ausente.
            GenerationError: Se a geração violar o schema estruturado.
        """
        pass

    @abstractmethod
    async def chat_tailoring(
        self,
        messages: list["ChatMessage"],
        job_description: str,
        user_dossier: dict[str, Any],
        prompt_skill_instructions: str,
    ) -> str:
        """Conversa interativamente com o candidato sobre a estratégia de tailoring do currículo.

        Args:
            messages: Histórico da conversa multi-turn.
            job_description: Texto do anúncio da vaga.
            user_dossier: Dossiê factual real do candidato.
            prompt_skill_instructions: Diretrizes da metodologia selecionada.

        Returns:
            str: Resposta consultiva gerada pelo modelo de IA.

        Raises:
            MissingApiKeyError: Se a chave do Gemini estiver ausente.
            AIError: Em caso de falha de comunicação ou resposta vazia.
        """
        pass

    @abstractmethod
    async def translate_resume_content(
        self,
        content: dict[str, Any],
        target_language: str,
    ) -> dict[str, Any]:
        """Traduz o conteúdo estruturado do currículo para o idioma alvo mantendo integridade factual.

        Args:
            content: Dicionário estruturado do currículo atual.
            target_language: Idioma de destino ('en-US', 'pt-BR', 'es-ES', etc.).

        Returns:
            dict[str, Any]: Conteúdo com textos traduzidos mantendo a mesma estrutura de chaves.

        Raises:
            MissingApiKeyError: Se a chave do Gemini estiver ausente.
            AIError: Em caso de falha de comunicação ou resposta vazia.
        """
        pass


class ChatMessage(BaseModel):
    """Representação de uma mensagem no histórico conversacional com o Copilot.

    Attributes:
        role: Papel da mensagem ('user' ou 'assistant' / 'model').
        content: Conteúdo textual da mensagem.
    """

    role: str
    content: str
