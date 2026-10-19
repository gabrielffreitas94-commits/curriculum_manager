"""Porta abstrata e DTOs para o agente Job Hunter (Arquitetura Hexagonal).

Define contratos puros de busca e ingestão de vagas externas,
sem acoplamento a frameworks, adaptadores ou serviços de aplicação.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict


class JobHunterSourceError(Exception):
    """Exceção base para falhas de obtenção e ingestão de fontes de vagas."""

    pass


class JobSourceRateLimitError(JobHunterSourceError):
    """Lançada quando a fonte externa aplica limitação de taxa (HTTP 429)."""

    pass


class JobSourceBlockedError(JobHunterSourceError):
    """Lançada quando o acesso à vaga é bloqueado por WAF, CAPTCHA ou HTTP 403."""

    pass


class JobSourceNetworkError(JobHunterSourceError):
    """Lançada quando ocorrem timeouts ou falhas de transporte/rede ao acessar a fonte."""

    pass


class ScrapedJobPosting(BaseModel):
    """DTO puro contendo os dados preliminares extraídos de uma vaga de emprego."""

    model_config = ConfigDict(extra="ignore")

    source_url: str
    company_name: str = "Empresa Confidencial"
    job_title: str = "Oportunidade Técnica"
    raw_description: str
    location: str | None = None
    work_model: str = "remote"
    salary_range: str | None = None


class JobSourcePort(ABC):
    """Interface abstrata para ingestão de oportunidades profissionais externas."""

    @abstractmethod
    async def fetch_job_posting(self, url: str) -> ScrapedJobPosting:
        """Obtém o conteúdo textual e metadados de uma vaga a partir de sua URL.

        Args:
            url: Endereço web público da oportunidade.

        Returns:
            ScrapedJobPosting: Dados estruturados preliminares extraídos da página.

        Raises:
            JobSourceBlockedError: Se a requisição for bloqueada por WAF/CAPTCHA/403.
            JobSourceRateLimitError: Se houver rate limiting persistente na fonte.
            JobSourceNetworkError: Em caso de falha de conexão persistente ou timeout.
            SSRFProtectionError: Se o destino resolver para rede restrita/privada.
            PayloadTooLargeError: Se a resposta exceder o limite seguro de bytes.
        """
        pass
