"""Adaptador concreto para coleta e ingestão de vagas externas via HTTP seguro.

Implementa a porta JobSourcePort consumindo app.core.url_scraper com
blindagem SSRF fail-closed, backoff exponencial em rate-limit e extração
estruturada de metadados de oportunidade.
"""

import asyncio
import time
from urllib.parse import urlparse

import httpx

from app.core.logging import get_logger
from app.core.url_scraper import (
    PayloadTooLargeError,
    SSRFProtectionError,
    UrlScraperError,
    safe_fetch_url,
)
from app.ports.job_hunter_port import (
    JobHunterSourceError,
    JobSourceBlockedError,
    JobSourceNetworkError,
    JobSourcePort,
    JobSourceRateLimitError,
    ScrapedJobPosting,
)

logger = get_logger(__name__)


class HttpJobSourceAdapter(JobSourcePort):
    """Adaptador HTTP com blindagem e resiliência para captura de vagas."""

    def __init__(
        self,
        max_retries: int = 2,
        backoff_seconds: float = 0.01,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Inicializa o adaptador HTTP de vagas.

        Args:
            max_retries: Quantidade máxima de tentativas adicionais para erros transitórios.
            backoff_seconds: Tempo base para espera exponencial entre retentativas.
            client: Cliente HTTP assíncrono opcional (para injeção e testes).
        """
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.client = client

    @staticmethod
    def _infer_company_from_url(url: str) -> str:
        """Infere o nome preliminar da empresa a partir do hostname da URL.

        Args:
            url: URL da vaga.

        Returns:
            str: Nome capitalizado da empresa ou 'Empresa Confidencial'.
        """
        try:
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").strip()
            if not hostname:
                return "Empresa Confidencial"

            parts = [part for part in hostname.split(".") if part]
            if not parts:
                return "Empresa Confidencial"

            known_tlds = {
                "com",
                "org",
                "net",
                "edu",
                "gov",
                "mil",
                "io",
                "ai",
                "co",
                "app",
                "dev",
                "tech",
                "br",
                "uk",
                "de",
                "fr",
                "ca",
                "me",
            }
            while len(parts) > 1 and parts[-1].lower() in known_tlds:
                parts.pop()

            main_label = parts[-1].strip()
            if main_label:
                return main_label.capitalize()
            return "Empresa Confidencial"
        except Exception:
            return "Empresa Confidencial"

    def _extract_metadata_from_text(self, url: str, raw_text: str) -> ScrapedJobPosting:
        """Extrai campos estruturados preliminares a partir do texto bruto da página.

        Args:
            url: URL de origem da vaga.
            raw_text: Texto limpo extraído da página HTML.

        Returns:
            ScrapedJobPosting: DTO com metadados e modelo de trabalho inferido.
        """
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        company_name: str | None = None
        job_title: str | None = None
        location: str | None = None
        salary_range: str | None = None

        for line in lines:
            lower_line = line.lower()

            # Nome da empresa
            if company_name is None:
                for prefix in ("empresa:", "company:"):
                    if lower_line.startswith(prefix):
                        val = line[len(prefix) :].strip()
                        if val:
                            company_name = val[:100]
                        break

            # Título da vaga / cargo
            if job_title is None:
                for prefix in ("vaga:", "cargo:", "role:", "title:"):
                    if lower_line.startswith(prefix):
                        val = line[len(prefix) :].strip()
                        if val:
                            job_title = val[:120]
                        break

            # Localização
            if location is None:
                for prefix in ("local:", "localização:", "location:"):
                    if lower_line.startswith(prefix):
                        val = line[len(prefix) :].strip()
                        if val:
                            location = val[:100]
                        break

            # Faixa salarial
            if salary_range is None:
                for prefix in ("salário:", "faixa salarial:", "salary:"):
                    if lower_line.startswith(prefix):
                        val = line[len(prefix) :].strip()
                        if val:
                            salary_range = val[:80]
                        break

        if not company_name:
            company_name = self._infer_company_from_url(url)

        if not job_title:
            job_title = lines[0][:120] if lines else "Oportunidade Técnica"

        lower_raw = raw_text.lower()
        if any(kw in lower_raw for kw in ("híbrido", "hibrido", "hybrid")):
            work_model = "hybrid"
        elif any(kw in lower_raw for kw in ("presencial", "on-site", "onsite")):
            work_model = "on-site"
        else:
            work_model = "remote"

        return ScrapedJobPosting(
            source_url=url,
            company_name=company_name or "Empresa Confidencial",
            job_title=job_title or "Oportunidade Técnica",
            raw_description=raw_text,
            location=location,
            work_model=work_model,
            salary_range=salary_range,
        )

    async def fetch_job_posting(self, url: str) -> ScrapedJobPosting:
        """Obtém e extrai dados estruturados de uma vaga a partir de sua URL.

        Args:
            url: URL pública da oportunidade profissional.

        Returns:
            ScrapedJobPosting: Dados estruturados e descrição da vaga.

        Raises:
            SSRFProtectionError: Se a URL apontar para destino proibido.
            PayloadTooLargeError: Se o documento exceder limites de tamanho.
            JobSourceBlockedError: Se a fonte bloquear o acesso (403, captcha, blocked).
            JobSourceRateLimitError: Se houver rate limiting após retentativas.
            JobSourceNetworkError: Se houver falha de transporte ou timeout persistente.
        """
        start_time = time.perf_counter()
        raw_text: str | None = None

        for attempt in range(self.max_retries + 1):
            try:
                raw_text = await safe_fetch_url(url=url, client=self.client)
                break
            except (SSRFProtectionError, PayloadTooLargeError) as exc:
                logger.warning(
                    "job_hunter_source_security_rejected",
                    url=url,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    attempt=attempt,
                )
                raise
            except UrlScraperError as exc:
                err_msg = str(exc).lower()

                # Bloqueio imediato (403, WAF, CAPTCHA) sem retry
                if any(term in err_msg for term in ("403", "forbidden", "blocked", "captcha")):
                    logger.warning(
                        "job_hunter_source_blocked",
                        url=url,
                        error=str(exc),
                        attempt=attempt,
                    )
                    raise JobSourceBlockedError(str(exc)) from exc

                # Limitação de taxa (429, Rate limit) com retentativa
                if any(term in err_msg for term in ("429", "rate limit", "too many requests")):
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.backoff_seconds * (attempt + 1))
                        continue
                    logger.warning(
                        "job_hunter_source_rate_limited",
                        url=url,
                        error=str(exc),
                        attempt=attempt,
                    )
                    raise JobSourceRateLimitError(str(exc)) from exc

                # Timeout ou falha genérica de rede com retentativa
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_seconds * (attempt + 1))
                    continue
                logger.warning(
                    "job_hunter_source_network_failed",
                    url=url,
                    error=str(exc),
                    attempt=attempt,
                )
                raise JobSourceNetworkError(str(exc)) from exc
            except JobHunterSourceError:
                raise
            except Exception as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_seconds * (attempt + 1))
                    continue
                logger.warning(
                    "job_hunter_source_network_failed",
                    url=url,
                    error=str(exc),
                    attempt=attempt,
                    exc_info=True,
                )
                raise JobSourceNetworkError(str(exc)) from exc

        if raw_text is None:
            raise JobSourceNetworkError("Falha ao obter conteúdo da vaga: resposta vazia.")

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        posting = self._extract_metadata_from_text(url=url, raw_text=raw_text)

        logger.info(
            "job_hunter_source_fetched",
            url=url,
            duration_ms=duration_ms,
            company_name=posting.company_name,
            job_title=posting.job_title,
            work_model=posting.work_model,
        )

        return posting
