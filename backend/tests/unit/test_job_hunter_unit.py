"""Testes unitários e BVA (Boundary Value Analysis) para o subsistema Job Hunter.

Cobre com 100% de linhas e branches:
- app.ports.job_hunter_port
- app.adapters.job_source_adapter
- app.services.job_hunter_service
- app.api.v1.deps (get_job_hunter_service)
- app.api.v1.schemas.job_hunter
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import ParseResult

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gemini_ai_adapter import GeminiAIAdapter
from app.adapters.job_source_adapter import HttpJobSourceAdapter
from app.api.v1.deps import get_job_hunter_service
from app.api.v1.schemas.job_hunter import (
    JobHunterGoalConfig,
    JobHunterItemResult,
    JobHunterRunResponse,
)
from app.core.url_scraper import (
    PayloadTooLargeError,
    ScraperTimeoutError,
    SSRFProtectionError,
    UrlScraperError,
)
from app.domain.models import Application, User
from app.ports.ai_port import (
    AIError,
    AIPort,
    JobAnalysisResult,
    MissingApiKeyError,
)
from app.ports.job_hunter_port import (
    JobHunterSourceError,
    JobSourceBlockedError,
    JobSourceNetworkError,
    JobSourcePort,
    JobSourceRateLimitError,
    ScrapedJobPosting,
)
from app.services.job_hunter_service import JobHunterService

# ============================================================================
# 1. TESTES DE PORTA E DTOS (app.ports.job_hunter_port)
# ============================================================================


class TestJobHunterPort:
    """Testes para DTOs, exceções e contrato abstrato de Job Hunter."""

    def test_job_hunter_exceptions_hierarchy(self) -> None:
        """Valida que todas as exceções de domínio herdam de JobHunterSourceError."""
        base_err = JobHunterSourceError("base error")
        rate_err = JobSourceRateLimitError("rate limited")
        blocked_err = JobSourceBlockedError("blocked")
        network_err = JobSourceNetworkError("network fail")

        assert isinstance(rate_err, JobHunterSourceError)
        assert isinstance(blocked_err, JobHunterSourceError)
        assert isinstance(network_err, JobHunterSourceError)
        assert str(base_err) == "base error"

    def test_scraped_job_posting_defaults_and_custom_values(self) -> None:
        """Valida inicialização do DTO ScrapedJobPosting com defaults e com atributos customizados."""
        posting_default = ScrapedJobPosting(
            source_url="https://example.com/job/1",
            raw_description="Descrição da oportunidade",
        )
        assert posting_default.company_name == "Empresa Confidencial"
        assert posting_default.job_title == "Oportunidade Técnica"
        assert posting_default.location is None
        assert posting_default.work_model == "remote"
        assert posting_default.salary_range is None

        posting_custom = ScrapedJobPosting(
            source_url="https://acme.org/jobs/42",
            company_name="Acme Corporation",
            job_title="Senior Python Architect",
            raw_description="Stack: FastAPI, Docker, PostgreSQL",
            location="São Paulo, SP",
            work_model="hybrid",
            salary_range="R$ 15.000 - R$ 20.000",
        )
        assert posting_custom.company_name == "Acme Corporation"
        assert posting_custom.job_title == "Senior Python Architect"
        assert posting_custom.work_model == "hybrid"
        assert posting_custom.location == "São Paulo, SP"
        assert posting_custom.salary_range == "R$ 15.000 - R$ 20.000"

    @pytest.mark.asyncio
    async def test_job_source_port_abstract_interface(self) -> None:
        """Valida a implementação concreta da interface abstrata JobSourcePort."""

        class DummyJobSource(JobSourcePort):
            async def fetch_job_posting(self, url: str) -> ScrapedJobPosting:
                # Chama o super para cobrir a linha 'pass' no método abstrato
                return await super().fetch_job_posting(url)  # type: ignore[safe-super]

        dummy = DummyJobSource()
        res = await dummy.fetch_job_posting("https://dummy.com")
        assert res is None


# ============================================================================
# 2. TESTES DO ADAPTADOR HTTP (app.adapters.job_source_adapter)
# ============================================================================


class TestHttpJobSourceAdapterCompanyInference:
    """Testes exaustivos para _infer_company_from_url cobrindo todos os branches."""

    def test_infer_company_from_url_with_multiple_subdomains_and_tlds(self) -> None:
        """Testa URL com múltiplos subdomínios e sufixos TLD conhecidos (.com.br)."""
        adapter = HttpJobSourceAdapter()
        assert adapter._infer_company_from_url("https://boards.acme.com.br/jobs/1") == "Acme"
        assert adapter._infer_company_from_url("http://careers.google.com/jobs") == "Google"
        assert adapter._infer_company_from_url("https://jobs.lever.co/vtex") == "Lever"
        assert adapter._infer_company_from_url("https://tech.startup.io") == "Startup"

    def test_infer_company_from_url_with_single_domain_and_single_tld(self) -> None:
        """Testa URL com apenas domínio e TLD único."""
        adapter = HttpJobSourceAdapter()
        assert adapter._infer_company_from_url("https://netflix.com") == "Netflix"
        assert adapter._infer_company_from_url("https://nubank.com.br") == "Nubank"

    def test_infer_company_from_url_all_known_tlds_and_one_part_remaining(self) -> None:
        """Testa quando todas as partes do hostname são TLDs (len(parts) > 1 até restar 1)."""
        adapter = HttpJobSourceAdapter()
        # 'com.br' tem 2 partes; 'br' é conhecido e desempilha; resta 'com'
        assert adapter._infer_company_from_url("https://com.br") == "Com"

    def test_infer_company_from_url_without_hostname_or_relative_path(self) -> None:
        """Testa URLs inválidas, relativas ou sem hostname retornando Empresa Confidencial."""
        adapter = HttpJobSourceAdapter()
        assert adapter._infer_company_from_url("not-a-url") == "Empresa Confidencial"
        assert adapter._infer_company_from_url("/relative/path/to/job") == "Empresa Confidencial"
        assert adapter._infer_company_from_url("") == "Empresa Confidencial"
        assert adapter._infer_company_from_url("   ") == "Empresa Confidencial"

    def test_infer_company_from_url_hostname_with_dots_only(self) -> None:
        """Testa hostname composto unicamente de pontos."""
        adapter = HttpJobSourceAdapter()
        fake_parsed = ParseResult(
            scheme="https",
            netloc="...",
            path="",
            params="",
            query="",
            fragment="",
        )
        with patch("app.adapters.job_source_adapter.urlparse", return_value=fake_parsed):
            assert adapter._infer_company_from_url("https://...") == "Empresa Confidencial"

    def test_infer_company_from_url_main_label_empty_after_strip(self) -> None:
        """Testa branch onde main_label é uma string vazia após strip() (linha 100)."""
        adapter = HttpJobSourceAdapter()
        fake_parsed = MagicMock()
        # "sub.   .com" após split gera ["sub", "   ", "com"]. "com" é pop(). Resta ["sub", "   "].
        # parts[-1] é "   ", que stripped resulta em "". Linha 100 é alcançada!
        fake_parsed.hostname = "sub.   .com"
        with patch("app.adapters.job_source_adapter.urlparse", return_value=fake_parsed):
            assert adapter._infer_company_from_url("https://sub.   .com") == "Empresa Confidencial"

    def test_infer_company_from_url_exception_handling(self) -> None:
        """Testa tratamento de exceção em urlparse retornando Empresa Confidencial."""
        adapter = HttpJobSourceAdapter()
        with patch(
            "app.adapters.job_source_adapter.urlparse", side_effect=ValueError("Invalid URL format")
        ):
            assert adapter._infer_company_from_url("https://crash.com") == "Empresa Confidencial"


class TestHttpJobSourceAdapterMetadataExtraction:
    """Testes exaustivos para _extract_metadata_from_text cobrindo todos os branches."""

    def test_extract_metadata_explicit_fields_and_hybrid_work_model(self) -> None:
        """Extrai campos explícitos e identifica modelo híbrido."""
        adapter = HttpJobSourceAdapter()
        raw_text = (
            "Empresa: Stone Pagamentos\n"
            "Vaga: Engenheiro de Software Sênior\n"
            "Local: Rio de Janeiro, RJ\n"
            "Salário: R$ 18.000\n"
            "Modelo de atuação: regime híbrido (2 dias presenciais)."
        )
        posting = adapter._extract_metadata_from_text("https://stone.com.br/job/1", raw_text)

        assert posting.company_name == "Stone Pagamentos"
        assert posting.job_title == "Engenheiro de Software Sênior"
        assert posting.location == "Rio de Janeiro, RJ"
        assert posting.salary_range == "R$ 18.000"
        assert posting.work_model == "hybrid"

    def test_extract_metadata_alternative_prefixes_and_onsite_work_model(self) -> None:
        """Extrai metadados usando prefixos em inglês e modelo presencial."""
        adapter = HttpJobSourceAdapter()
        raw_text = (
            "Company: Nubank\n"
            "Role: Staff Engineer\n"
            "Location: São Paulo Headquarters\n"
            "Salary: R$ 25.000 - R$ 30.000\n"
            "Regime totalmente presencial no escritório central."
        )
        posting = adapter._extract_metadata_from_text("https://nubank.com.br/vaga", raw_text)

        assert posting.company_name == "Nubank"
        assert posting.job_title == "Staff Engineer"
        assert posting.location == "São Paulo Headquarters"
        assert posting.salary_range == "R$ 25.000 - R$ 30.000"
        assert posting.work_model == "on-site"

    def test_extract_metadata_prefixes_cargo_localizacao_faixa_salarial_title(self) -> None:
        """Testa todas as variantes de prefixos: cargo, localização, faixa salarial e title."""
        adapter = HttpJobSourceAdapter()
        raw_text = (
            "company: MercadoLivre\n"
            "cargo: Arquiteto de Soluções\n"
            "localização: Florianópolis, SC\n"
            "faixa salarial: R$ 22.000 CLT\n"
            "Vaga 100% remota."
        )
        posting = adapter._extract_metadata_from_text("https://mercadolivre.com", raw_text)

        assert posting.company_name == "MercadoLivre"
        assert posting.job_title == "Arquiteto de Soluções"
        assert posting.location == "Florianópolis, SC"
        assert posting.salary_range == "R$ 22.000 CLT"
        assert posting.work_model == "remote"

        # Variação com 'title:'
        raw_text_title = (
            "title: Backend Lead Developer\nlocal: Belo Horizonte, MG\nsalário: A combinar\n"
        )
        posting_title = adapter._extract_metadata_from_text("https://totvs.com.br", raw_text_title)
        assert posting_title.company_name == "Totvs"
        assert posting_title.job_title == "Backend Lead Developer"

    def test_extract_metadata_empty_values_after_prefix(self) -> None:
        """Testa linhas com prefixo reconhecido mas conteúdo vazio após o prefixo."""
        adapter = HttpJobSourceAdapter()
        raw_text = (
            "Empresa:   \n"
            "Vaga:   \n"
            "Local:   \n"
            "Salário:   \n"
            "Desenvolvimento de microsserviços em Go e Python."
        )
        posting = adapter._extract_metadata_from_text("https://careers.uber.com/job/99", raw_text)

        assert posting.company_name == "Uber"
        # Sem cargo explícito, job_title assume a primeira linha válida do texto ('Empresa:')
        assert posting.job_title == "Empresa:"
        assert posting.location is None
        assert posting.salary_range is None
        assert posting.work_model == "remote"

    def test_extract_metadata_empty_text_fallbacks(self) -> None:
        """Testa raw_text completamente vazio caindo em Oportunidade Técnica e remote."""
        adapter = HttpJobSourceAdapter()
        posting = adapter._extract_metadata_from_text("not-a-url", "")

        assert posting.company_name == "Empresa Confidencial"
        assert posting.job_title == "Oportunidade Técnica"
        assert posting.work_model == "remote"
        assert posting.raw_description == ""

    def test_extract_metadata_work_model_keywords(self) -> None:
        """Testa palavras-chave de detecção de modelo de trabalho: hybrid, onsite e remote."""
        adapter = HttpJobSourceAdapter()

        # hibrido sem acento e hybrid
        posting_h1 = adapter._extract_metadata_from_text(
            "https://a.com", "Vaga Dev\nAtuação em modelo hibrido"
        )
        assert posting_h1.work_model == "hybrid"

        posting_h2 = adapter._extract_metadata_from_text(
            "https://a.com", "Vaga Dev\nHybrid work model"
        )
        assert posting_h2.work_model == "hybrid"

        # on-site e onsite
        posting_o1 = adapter._extract_metadata_from_text(
            "https://a.com", "Vaga Dev\nOn-site requirements"
        )
        assert posting_o1.work_model == "on-site"

        posting_o2 = adapter._extract_metadata_from_text(
            "https://a.com", "Vaga Dev\nOnsite work in office"
        )
        assert posting_o2.work_model == "on-site"

        # fallback remoto
        posting_r = adapter._extract_metadata_from_text(
            "https://a.com", "Vaga Dev\nAtuação 100% home office e flexível"
        )
        assert posting_r.work_model == "remote"

    def test_extract_metadata_subsequent_duplicate_prefix_lines_ignored(self) -> None:
        """Testa que prefixos subsequentes são ignorados quando os campos já estão preenchidos."""
        adapter = HttpJobSourceAdapter()
        raw_text = (
            "Empresa: Primeira Empresa\n"
            "Empresa: Segunda Empresa\n"
            "Vaga: Cargo Primário\n"
            "Vaga: Cargo Secundário\n"
            "Local: Cidade Primária\n"
            "Local: Cidade Secundária\n"
            "Salário: Salário Primário\n"
            "Salário: Salário Secundário\n"
        )
        posting = adapter._extract_metadata_from_text("https://test.com", raw_text)
        assert posting.company_name == "Primeira Empresa"
        assert posting.job_title == "Cargo Primário"
        assert posting.location == "Cidade Primária"
        assert posting.salary_range == "Salário Primário"

    def test_extract_metadata_or_fallback_when_company_and_job_title_empty_strings(self) -> None:
        """Testa os branches 'or Empresa Confidencial' e 'or Oportunidade Técnica' na construção do DTO."""
        adapter = HttpJobSourceAdapter()
        with (
            patch.object(adapter, "_infer_company_from_url", return_value=""),
            patch.object(
                adapter, "_extract_metadata_from_text", wraps=adapter._extract_metadata_from_text
            ),
        ):
            # Passando texto com apenas quebras de linha
            posting = adapter._extract_metadata_from_text("https://test.com", "\n\n")
            assert posting.company_name == "Empresa Confidencial"
            assert posting.job_title == "Oportunidade Técnica"


class TestHttpJobSourceAdapterFetchJobPosting:
    """Testes com retentativas, fallbacks e guardrails de segurança para fetch_job_posting."""

    @pytest.mark.asyncio
    async def test_fetch_job_posting_happy_path(self) -> None:
        """Testa o fluxo feliz de busca e extração de vaga com cliente injetado."""
        mock_client = MagicMock(spec=httpx.AsyncClient)
        adapter = HttpJobSourceAdapter(max_retries=2, backoff_seconds=0.001, client=mock_client)

        raw_html_text = "Empresa: AWS\nVaga: Cloud Engineer\nLocal: SP\nTrabalho remoto."
        with patch(
            "app.adapters.job_source_adapter.safe_fetch_url",
            new_callable=AsyncMock,
            return_value=raw_html_text,
        ) as mock_fetch:
            posting = await adapter.fetch_job_posting("https://aws.amazon.com/jobs/1")

            assert mock_fetch.call_count == 1
            assert posting.company_name == "AWS"
            assert posting.job_title == "Cloud Engineer"
            assert posting.work_model == "remote"

    @pytest.mark.asyncio
    async def test_fetch_job_posting_ssrf_protection_guardrail(self) -> None:
        """VETOR DE AMEAÇA: CWE-918 (Server-Side Request Forgery).
        Um atacante tenta submeter URLs para redes privadas (127.0.0.1, 169.254.169.254).

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        O adaptador deve rejeitar imediatamente na tentativa 0 sem tentar retentativa.

        RISCO DE REGRESSÃO SILENCIOSA:
        Retentar requisições bloqueadas por SSRF geraria tráfego desnecessário e risco.

        PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
        SSRFProtectionError deve ser relançado imediatamente sem retries.
        """
        adapter = HttpJobSourceAdapter(max_retries=3, backoff_seconds=0.001)

        with patch(
            "app.adapters.job_source_adapter.safe_fetch_url",
            new_callable=AsyncMock,
            side_effect=SSRFProtectionError("IP restrito detectado"),
        ) as mock_fetch:
            with pytest.raises(SSRFProtectionError) as exc_info:
                await adapter.fetch_job_posting("http://169.254.169.254/latest/meta-data")

            assert "IP restrito" in str(exc_info.value)
            assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_job_posting_payload_too_large_guardrail(self) -> None:
        """VETOR DE AMEAÇA: CWE-400 (Resource Exhaustion / Large Payload DoS).
        Um portal retorna stream gigantesco ou arquivo binário com centenas de megabytes.

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        Rejeitar imediatamente na tentativa 0 com PayloadTooLargeError sem retentativas.

        RISCO DE REGRESSÃO SILENCIOSA:
        Retentar downloads que excedem o buffer estoura a memória do container.

        PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
        PayloadTooLargeError deve ser relançado na primeira falha.
        """
        adapter = HttpJobSourceAdapter(max_retries=3, backoff_seconds=0.001)

        with patch(
            "app.adapters.job_source_adapter.safe_fetch_url",
            new_callable=AsyncMock,
            side_effect=PayloadTooLargeError("Conteúdo excedeu 2MB"),
        ) as mock_fetch:
            with pytest.raises(PayloadTooLargeError):
                await adapter.fetch_job_posting("https://large-dump.com/job")

            assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_job_posting_waf_blocked_403_no_retries(self) -> None:
        """Testa bloqueio por 403, WAF ou CAPTCHA lançando JobSourceBlockedError imediatamente."""
        adapter = HttpJobSourceAdapter(max_retries=3, backoff_seconds=0.001)

        for err_pattern in ("HTTP 403 Forbidden", "Blocked by Cloudflare", "CAPTCHA challenge"):
            with patch(
                "app.adapters.job_source_adapter.safe_fetch_url",
                new_callable=AsyncMock,
                side_effect=UrlScraperError(err_pattern),
            ) as mock_fetch:
                with pytest.raises(JobSourceBlockedError) as exc_info:
                    await adapter.fetch_job_posting("https://protected.com/job")

                assert err_pattern in str(exc_info.value)
                assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_job_posting_rate_limit_429_retries_and_exhaustion(self) -> None:
        """Testa retentativas exponenciais em HTTP 429 culminando em JobSourceRateLimitError."""
        adapter = HttpJobSourceAdapter(max_retries=2, backoff_seconds=0.001)

        with patch(
            "app.adapters.job_source_adapter.safe_fetch_url",
            new_callable=AsyncMock,
            side_effect=UrlScraperError("HTTP 429 Too Many Requests"),
        ) as mock_fetch:
            with pytest.raises(JobSourceRateLimitError) as exc_info:
                await adapter.fetch_job_posting("https://rate-limited.com/job")

            assert "429" in str(exc_info.value)
            # max_retries = 2 significa tentativa inicial (0) + 2 retentativas = 3 chamadas
            assert mock_fetch.call_count == 3

    @pytest.mark.asyncio
    async def test_fetch_job_posting_rate_limit_429_success_on_second_attempt(self) -> None:
        """Testa recuperação bem-sucedida após rate limiting na primeira tentativa."""
        adapter = HttpJobSourceAdapter(max_retries=2, backoff_seconds=0.001)

        with patch(
            "app.adapters.job_source_adapter.safe_fetch_url",
            new_callable=AsyncMock,
            side_effect=[
                UrlScraperError("429 rate limit exceeded"),
                "Empresa: Recovery\nVaga: Dev",
            ],
        ) as mock_fetch:
            posting = await adapter.fetch_job_posting("https://recovered.com/job")

            assert mock_fetch.call_count == 2
            assert posting.company_name == "Recovery"

    @pytest.mark.asyncio
    async def test_fetch_job_posting_scraper_timeout_retries_and_exhaustion(self) -> None:
        """Testa timeout de scraper esgotando retentativas e lançando JobSourceNetworkError."""
        adapter = HttpJobSourceAdapter(max_retries=2, backoff_seconds=0.001)

        with patch(
            "app.adapters.job_source_adapter.safe_fetch_url",
            new_callable=AsyncMock,
            side_effect=ScraperTimeoutError("Timeout de conexão após 10s"),
        ) as mock_fetch:
            with pytest.raises(JobSourceNetworkError) as exc_info:
                await adapter.fetch_job_posting("https://timeout.com/job")

            assert "Timeout" in str(exc_info.value)
            assert mock_fetch.call_count == 3

    @pytest.mark.asyncio
    async def test_fetch_job_posting_generic_scraper_error_success_on_retry(self) -> None:
        """Testa erro genérico de UrlScraperError recuperado na segunda tentativa."""
        adapter = HttpJobSourceAdapter(max_retries=2, backoff_seconds=0.001)

        with patch(
            "app.adapters.job_source_adapter.safe_fetch_url",
            new_callable=AsyncMock,
            side_effect=[
                UrlScraperError("Falha de conexão DNS"),
                "Empresa: DNS Fix\nVaga: Net Admin",
            ],
        ) as mock_fetch:
            posting = await adapter.fetch_job_posting("https://dns.com/job")

            assert mock_fetch.call_count == 2
            assert posting.company_name == "DNS Fix"

    @pytest.mark.asyncio
    async def test_fetch_job_posting_direct_job_hunter_source_error_reraised(self) -> None:
        """Testa JobHunterSourceError levantado diretamente no loop sendo repassado."""
        adapter = HttpJobSourceAdapter(max_retries=2, backoff_seconds=0.001)

        with patch(
            "app.adapters.job_source_adapter.safe_fetch_url",
            new_callable=AsyncMock,
            side_effect=JobSourceBlockedError("Direct block error"),
        ) as mock_fetch:
            with pytest.raises(JobSourceBlockedError):
                await adapter.fetch_job_posting("https://custom-error.com")

            assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_job_posting_unexpected_exception_retries_and_exhaustion(self) -> None:
        """Testa exceção inesperada (Exception) esgotando tentativas e virando JobSourceNetworkError."""
        adapter = HttpJobSourceAdapter(max_retries=2, backoff_seconds=0.001)

        with patch(
            "app.adapters.job_source_adapter.safe_fetch_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Falha inesperada no subsistema de rede"),
        ) as mock_fetch:
            with pytest.raises(JobSourceNetworkError) as exc_info:
                await adapter.fetch_job_posting("https://crash.com/job")

            assert "Falha inesperada" in str(exc_info.value)
            assert mock_fetch.call_count == 3

    @pytest.mark.asyncio
    async def test_fetch_job_posting_unexpected_exception_success_on_retry(self) -> None:
        """Testa exceção inesperada recuperada com sucesso na retentativa."""
        adapter = HttpJobSourceAdapter(max_retries=2, backoff_seconds=0.001)

        with patch(
            "app.adapters.job_source_adapter.safe_fetch_url",
            new_callable=AsyncMock,
            side_effect=[
                RuntimeError("Transient OS socket issue"),
                "Empresa: Socket OK\nVaga: SysDev",
            ],
        ) as mock_fetch:
            posting = await adapter.fetch_job_posting("https://socket.com/job")

            assert mock_fetch.call_count == 2
            assert posting.company_name == "Socket OK"

    @pytest.mark.asyncio
    async def test_fetch_job_posting_empty_raw_text_branch_when_retries_negative(self) -> None:
        """Testa branch 'if raw_text is None' quando o loop não roda (ex: max_retries < 0)."""
        adapter = HttpJobSourceAdapter(max_retries=-1, backoff_seconds=0.001)

        with pytest.raises(JobSourceNetworkError) as exc_info:
            await adapter.fetch_job_posting("https://never-attempted.com")

        assert "resposta vazia" in str(exc_info.value)


# ============================================================================
# 3. TESTES DO SERVIÇO JOB HUNTER (app.services.job_hunter_service)
# ============================================================================


class TestJobHunterServiceDossierAndDuplication:
    """Testes de normalização de dossiê factual e verificação de duplicidade."""

    def test_build_match_dossier_all_data_types(self) -> None:
        """Testa _build_match_dossier cobrindo objetos ORM, dicionários e tipos primitivos."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_ai = AsyncMock(spec=AIPort)
        mock_source = AsyncMock(spec=JobSourcePort)
        service = JobHunterService(mock_db, mock_ai, mock_source)

        raw_dossier = {
            "skills": [
                SimpleNamespace(name="Python"),
                {"name": "FastAPI"},
                "Docker",
            ],
            "experiences": [
                # Objeto com atributos preenchidos
                SimpleNamespace(
                    company_name="Acme",
                    position_title="Software Architect",
                    tech_stack=["Python", "FastAPI"],
                    bullet_points=["Criou arquitetura hexagonal", "Reduziu latência em 40%"],
                ),
                # Dicionário com dados preenchidos
                {
                    "company_name": "Beta Labs",
                    "position_title": "Tech Lead",
                    "tech_stack": ["Go", "Kubernetes"],
                    "bullet_points": ["Liderou equipe de 8 devs"],
                },
                # Dicionário com campos None/vazios
                {
                    "company_name": None,
                    "position_title": None,
                    "tech_stack": None,
                    "bullet_points": None,
                },
                # Primitivo (string simples)
                "Experiência não estruturada legada",
                # Objeto com atributos vazios
                SimpleNamespace(
                    company_name="",
                    position_title="",
                    tech_stack=[],
                    bullet_points=[],
                ),
            ],
            "certifications": [
                SimpleNamespace(name="AWS Certified Solutions Architect"),
                {"name": "Certified Kubernetes Administrator (CKA)"},
                "Terraform Associate",
            ],
        }

        normalized = service._build_match_dossier(raw_dossier)

        assert normalized["skills"] == ["Python", "FastAPI", "Docker"]
        assert len(normalized["experiences"]) == 5
        assert normalized["experiences"][0]["company_name"] == "Acme"
        assert normalized["experiences"][1]["position_title"] == "Tech Lead"
        assert normalized["experiences"][2]["company_name"] == ""
        assert normalized["experiences"][2]["tech_stack"] == []
        assert normalized["experiences"][3]["company_name"] == ""
        assert normalized["experiences"][4]["company_name"] == ""
        assert normalized["certifications"] == [
            "AWS Certified Solutions Architect",
            "Certified Kubernetes Administrator (CKA)",
            "Terraform Associate",
        ]

    def test_build_match_dossier_empty(self) -> None:
        """Testa _build_match_dossier com dicionário vazio."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_ai = AsyncMock(spec=AIPort)
        mock_source = AsyncMock(spec=JobSourcePort)
        service = JobHunterService(mock_db, mock_ai, mock_source)

        normalized = service._build_match_dossier({})
        assert normalized == {"skills": [], "experiences": [], "certifications": []}

    @pytest.mark.asyncio
    async def test_is_duplicate_application_with_and_without_source_url(
        self, db_session: AsyncSession
    ) -> None:
        """Testa _is_duplicate_application tanto por job_url quanto por par (company, title)."""
        mock_ai = AsyncMock(spec=AIPort)
        mock_source = AsyncMock(spec=JobSourcePort)
        service = JobHunterService(db_session, mock_ai, mock_source)

        user = User(
            firebase_uid="uid-dup-test",
            email="dup@test.com",
            full_name="Duplicate Tester",
        )
        db_session.add(user)
        await db_session.flush()

        app = Application(
            user_id=user.id,
            company_name="Acme Corp",
            job_title="Senior Python Engineer",
            job_url="https://acme.com/jobs/101",
            job_description="Requisitos: Python, FastAPI e Cloud AWS",
            status="saved",
        )
        db_session.add(app)
        await db_session.commit()

        # 1. Match por URL idêntica
        dup_url = await service._is_duplicate_application(
            user_id=user.id,
            source_url="https://acme.com/jobs/101",
            company_name="Outra Empresa",
            job_title="Outro Cargo",
        )
        assert dup_url is True

        # 2. Match por (empresa, cargo) sem URL informada
        dup_company_title = await service._is_duplicate_application(
            user_id=user.id,
            source_url="",
            company_name="  ACME CORP  ",
            job_title="  senior python engineer  ",
        )
        assert dup_company_title is True

        # 3. Não duplicada
        not_dup = await service._is_duplicate_application(
            user_id=user.id,
            source_url="https://other.com/jobs/999",
            company_name="Other Corp",
            job_title="Junior QA",
        )
        assert not_dup is False

        # 4. Não duplicada com URL vazia
        not_dup_no_url = await service._is_duplicate_application(
            user_id=user.id,
            source_url="   ",
            company_name="Unseen Company",
            job_title="Unknown Role",
        )
        assert not_dup_no_url is False


class TestJobHunterServiceCareerGoals:
    """Testes exaustivos para _matches_career_goals."""

    def test_matches_career_goals_excluded_companies(self) -> None:
        """Testa descarte por lista de exclusão de empresas (blocklist)."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_ai = AsyncMock(spec=AIPort)
        mock_source = AsyncMock(spec=JobSourcePort)
        service = JobHunterService(mock_db, mock_ai, mock_source)

        posting = ScrapedJobPosting(
            source_url="https://blocked.com",
            company_name="Consultoria ExploraDev",
            job_title="Engenheiro de Software",
            raw_description="Atuação em cliente bancário.",
            work_model="remote",
        )

        goals_blocked = JobHunterGoalConfig(
            source_urls=["https://blocked.com"],
            excluded_companies=["ExploraDev", "   "],  # Testa string vazia após strip
        )
        ok, reason = service._matches_career_goals(posting, "Engenheiro de Software", goals_blocked)
        assert ok is False
        assert "Consultoria ExploraDev" in reason
        assert "lista de exclusão" in reason

        # Empresa permitida
        goals_allowed = JobHunterGoalConfig(
            source_urls=["https://blocked.com"],
            excluded_companies=["Outra Empresa"],
        )
        ok_allowed, _ = service._matches_career_goals(
            posting, "Engenheiro de Software", goals_allowed
        )
        assert ok_allowed is True

    def test_matches_career_goals_allowed_work_models(self) -> None:
        """Testa descarte por modelo de trabalho não aceito."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_ai = AsyncMock(spec=AIPort)
        mock_source = AsyncMock(spec=JobSourcePort)
        service = JobHunterService(mock_db, mock_ai, mock_source)

        posting_onsite = ScrapedJobPosting(
            source_url="https://job.com",
            company_name="Tech Corp",
            job_title="Engenheiro",
            raw_description="Presencial em SP",
            work_model="on-site",
        )

        goals_remote_only = JobHunterGoalConfig(
            source_urls=["https://job.com"],
            allowed_work_models=["remote", "hybrid"],
        )
        ok, reason = service._matches_career_goals(posting_onsite, "Engenheiro", goals_remote_only)
        assert ok is False
        assert "Modelo de trabalho 'on-site' incompatível" in reason

        # Modelo aceito
        goals_onsite_ok = JobHunterGoalConfig(
            source_urls=["https://job.com"],
            allowed_work_models=["on-site"],
        )
        ok_model, _ = service._matches_career_goals(posting_onsite, "Engenheiro", goals_onsite_ok)
        assert ok_model is True

        # Sem restrição de modelos (lista vazia)
        goals_empty_models = JobHunterGoalConfig(
            source_urls=["https://job.com"],
            allowed_work_models=["remote"],
        )
        goals_empty_models.allowed_work_models = []  # type: ignore[assignment]
        ok_empty, _ = service._matches_career_goals(
            posting_onsite, "Engenheiro", goals_empty_models
        )
        assert ok_empty is True

    def test_matches_career_goals_target_roles(self) -> None:
        """Testa correspondência e descarte por escopo de cargos-alvo (target_roles)."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_ai = AsyncMock(spec=AIPort)
        mock_source = AsyncMock(spec=JobSourcePort)
        service = JobHunterService(mock_db, mock_ai, mock_source)

        posting = ScrapedJobPosting(
            source_url="https://job.com",
            company_name="Tech Corp",
            job_title="Especialista em Nuvem",
            raw_description="Desenvolvimento em Python e arquitetura Cloud AWS.",
            work_model="remote",
        )

        # 1. Match em analyzed_title
        goals_match_analyzed = JobHunterGoalConfig(
            source_urls=["https://job.com"],
            target_roles=["Software Architect", "   "],
        )
        ok_a, _ = service._matches_career_goals(
            posting, "Senior Software Architect", goals_match_analyzed
        )
        assert ok_a is True

        # 2. Match em posting.job_title
        goals_match_posting = JobHunterGoalConfig(
            source_urls=["https://job.com"],
            target_roles=["Especialista"],
        )
        ok_p, _ = service._matches_career_goals(posting, "Outro Título", goals_match_posting)
        assert ok_p is True

        # 3. Match em raw_description
        goals_match_desc = JobHunterGoalConfig(
            source_urls=["https://job.com"],
            target_roles=["Cloud AWS"],
        )
        ok_d, _ = service._matches_career_goals(posting, "Outro Título", goals_match_desc)
        assert ok_d is True

        # 4. Mismatch total de cargos-alvo
        goals_mismatch = JobHunterGoalConfig(
            source_urls=["https://job.com"],
            target_roles=["Product Designer", "Scrum Master"],
        )
        ok_m, reason_m = service._matches_career_goals(posting, "Outro Título", goals_mismatch)
        assert ok_m is False
        assert "fora do escopo de cargos-alvo" in reason_m

        # 5. Sem target_roles (vazio)
        goals_empty_roles = JobHunterGoalConfig(
            source_urls=["https://job.com"],
            target_roles=[],
        )
        ok_e, _ = service._matches_career_goals(posting, "Outro Título", goals_empty_roles)
        assert ok_e is True


class TestJobHunterServiceHuntAndTriage:
    """Testes de integração de fluxo completo para hunt_and_triage cobrindo todas as decisões."""

    @pytest.mark.asyncio
    async def test_hunt_and_triage_all_five_source_errors_fail_closed(
        self, db_session: AsyncSession
    ) -> None:
        """Valida tratamento fail-closed de todos os 5 erros de ingestão de fonte externa."""
        mock_ai = AsyncMock(spec=AIPort)
        mock_source = AsyncMock(spec=JobSourcePort)

        # Configura respostas sequenciais com cada tipo de exceção
        mock_source.fetch_job_posting.side_effect = [
            SSRFProtectionError("Blocked private IP"),
            PayloadTooLargeError("Exceeded 2MB"),
            JobSourceRateLimitError("Rate limited 429"),
            JobSourceBlockedError("Blocked 403"),
            JobSourceNetworkError("Connection timed out"),
        ]

        service = JobHunterService(db_session, mock_ai, mock_source)
        user = User(firebase_uid="uid-src-err", email="err@test.com", full_name="Err Tester")
        db_session.add(user)
        await db_session.flush()

        goals = JobHunterGoalConfig(
            source_urls=[
                "https://e1.com",
                "https://e2.com",
                "https://e3.com",
                "https://e4.com",
                "https://e5.com",
            ]
        )

        with patch("app.services.job_hunter_service.ProfileService") as mock_profile_cls:
            mock_profile = mock_profile_cls.return_value
            mock_profile.get_full_dossier = AsyncMock(return_value={})

            resp = await service.hunt_and_triage(user, goals)

        assert resp.total_sources == 5
        assert resp.failed_count == 5
        assert resp.processed_count == 0
        assert len(resp.results) == 5

        assert resp.results[0].error_code == "SSRF_BLOCKED"
        assert resp.results[1].error_code == "PAYLOAD_TOO_LARGE"
        assert resp.results[2].error_code == "RATE_LIMITED"
        assert resp.results[3].error_code == "SOURCE_BLOCKED"
        assert resp.results[4].error_code == "NETWORK_ERROR"

    @pytest.mark.asyncio
    async def test_hunt_and_triage_skipped_duplicate_posting(
        self, db_session: AsyncSession
    ) -> None:
        """Valida detecção de vaga já presente no ATS marcando skipped_duplicate."""
        mock_ai = AsyncMock(spec=AIPort)
        mock_source = AsyncMock(spec=JobSourcePort)
        mock_source.fetch_job_posting.return_value = ScrapedJobPosting(
            source_url="https://acme.com/vaga/1",
            company_name="Acme",
            job_title="Software Engineer",
            raw_description="Python, FastAPI, Docker",
            work_model="remote",
        )

        service = JobHunterService(db_session, mock_ai, mock_source)
        user = User(firebase_uid="uid-skip-dup", email="skip@test.com", full_name="Skip Tester")
        db_session.add(user)
        await db_session.flush()

        goals = JobHunterGoalConfig(source_urls=["https://acme.com/vaga/1"])

        with (
            patch("app.services.job_hunter_service.ProfileService") as mock_profile_cls,
            patch.object(service, "_is_duplicate_application", return_value=True),
        ):
            mock_profile_cls.return_value.get_full_dossier = AsyncMock(return_value={})
            resp = await service.hunt_and_triage(user, goals)

        assert resp.total_sources == 1
        assert resp.skipped_duplicate_count == 1
        assert resp.processed_count == 1
        assert resp.results[0].decision == "skipped_duplicate"
        assert mock_ai.analyze_job.call_count == 0

    @pytest.mark.asyncio
    async def test_hunt_and_triage_missing_api_key_raises_400_guardrail(
        self, db_session: AsyncSession
    ) -> None:
        """VETOR DE AMEAÇA: CWE-287 / Falha de Configuração de Chaves (BYOK).
        O usuário tenta executar o pipeline de triagem por IA sem fornecer sua chave de API.

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        O serviço deve interromper o pipeline e levantar HTTPException(400) imediato.

        RISCO DE REGRESSÃO SILENCIOSA:
        Tratar MissingApiKeyError como falha silenciosa de fonte deixaria o usuário sem feedback.

        PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
        MissingApiKeyError deve disparar HTTPException com status_code 400.
        """
        mock_ai = AsyncMock(spec=AIPort)
        mock_ai.analyze_job.side_effect = MissingApiKeyError("API key não encontrada")
        mock_source = AsyncMock(spec=JobSourcePort)
        mock_source.fetch_job_posting.return_value = ScrapedJobPosting(
            source_url="https://acme.com/vaga/1",
            company_name="Acme",
            job_title="Dev",
            raw_description="Python",
        )

        service = JobHunterService(db_session, mock_ai, mock_source)
        user = User(firebase_uid="uid-no-key", email="nokey@test.com", full_name="NoKey")
        db_session.add(user)
        await db_session.flush()

        goals = JobHunterGoalConfig(source_urls=["https://acme.com/vaga/1"])

        with patch("app.services.job_hunter_service.ProfileService") as mock_profile_cls:
            mock_profile_cls.return_value.get_full_dossier = AsyncMock(return_value={})
            with pytest.raises(HTTPException) as exc_info:
                await service.hunt_and_triage(user, goals)

            assert exc_info.value.status_code == 400
            assert "Chave de API do Gemini não configurada" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_hunt_and_triage_ai_error_handled_as_failed_source(
        self, db_session: AsyncSession
    ) -> None:
        """Valida que falhas temporárias na IA (AIError) registram AI_EXTRACTION_ERROR."""
        mock_ai = AsyncMock(spec=AIPort)
        mock_ai.analyze_job.side_effect = AIError("Gemini overload 503")
        mock_source = AsyncMock(spec=JobSourcePort)
        mock_source.fetch_job_posting.return_value = ScrapedJobPosting(
            source_url="https://acme.com/vaga/1",
            company_name="Acme",
            job_title="Dev",
            raw_description="Python",
        )

        service = JobHunterService(db_session, mock_ai, mock_source)
        user = User(firebase_uid="uid-ai-err", email="aierr@test.com", full_name="AIErr")
        db_session.add(user)
        await db_session.flush()

        goals = JobHunterGoalConfig(source_urls=["https://acme.com/vaga/1"])

        with patch("app.services.job_hunter_service.ProfileService") as mock_profile_cls:
            mock_profile_cls.return_value.get_full_dossier = AsyncMock(return_value={})
            resp = await service.hunt_and_triage(user, goals)

        assert resp.failed_count == 1
        assert resp.results[0].decision == "failed_source"
        assert resp.results[0].error_code == "AI_EXTRACTION_ERROR"

    @pytest.mark.asyncio
    async def test_hunt_and_triage_title_fallback_when_empty_or_whitespace(
        self, db_session: AsyncSession
    ) -> None:
        """Testa fallback de effective_title quando job_analysis.job_title é vazio ou whitespace."""
        mock_ai = AsyncMock(spec=AIPort)
        # job_title com espaços em branco para cobrir o branch 'if not effective_title'
        mock_ai.analyze_job.return_value = JobAnalysisResult(
            job_title="   ",
            seniority_level="Senior",
            mandatory_requirements=["Python"],
            desirable_requirements=[],
            keywords=["Python"],
        )
        mock_source = AsyncMock(spec=JobSourcePort)
        mock_source.fetch_job_posting.return_value = ScrapedJobPosting(
            source_url="https://acme.com/vaga/1",
            company_name="Acme",
            job_title="Engenheiro Python Original",
            raw_description="Python avançado",
            work_model="remote",
        )

        service = JobHunterService(db_session, mock_ai, mock_source)
        user = User(firebase_uid="uid-title-fb", email="fb@test.com", full_name="TitleFB")
        db_session.add(user)
        await db_session.flush()

        goals = JobHunterGoalConfig(
            source_urls=["https://acme.com/vaga/1"],
            min_match_score=0.0,
            auto_pre_apply=False,
        )

        with patch("app.services.job_hunter_service.ProfileService") as mock_profile_cls:
            mock_profile_cls.return_value.get_full_dossier = AsyncMock(return_value={})
            resp = await service.hunt_and_triage(user, goals)

        assert resp.results[0].job_title == "Engenheiro Python Original"

    @pytest.mark.asyncio
    async def test_hunt_and_triage_rejected_criteria_mismatch(
        self, db_session: AsyncSession
    ) -> None:
        """Valida rejeição por incompatibilidade com metas de carreira (ex: empresa na blocklist)."""
        mock_ai = AsyncMock(spec=AIPort)
        mock_ai.analyze_job.return_value = JobAnalysisResult(
            job_title="Backend Developer",
            seniority_level="Pleno",
            mandatory_requirements=["Python"],
            desirable_requirements=[],
            keywords=["Python"],
        )
        mock_source = AsyncMock(spec=JobSourcePort)
        mock_source.fetch_job_posting.return_value = ScrapedJobPosting(
            source_url="https://evil.com/vaga",
            company_name="Evil Corp",
            job_title="Backend Developer",
            raw_description="Python",
            work_model="remote",
        )

        service = JobHunterService(db_session, mock_ai, mock_source)
        user = User(firebase_uid="uid-crit-mismatch", email="mismatch@test.com", full_name="MM")
        db_session.add(user)
        await db_session.flush()

        goals = JobHunterGoalConfig(
            source_urls=["https://evil.com/vaga"],
            excluded_companies=["Evil Corp"],
        )

        with patch("app.services.job_hunter_service.ProfileService") as mock_profile_cls:
            mock_profile_cls.return_value.get_full_dossier = AsyncMock(return_value={})
            resp = await service.hunt_and_triage(user, goals)

        assert resp.rejected_count == 1
        assert resp.processed_count == 1
        assert resp.results[0].decision == "rejected_criteria_mismatch"
        assert "Evil Corp" in resp.results[0].reason

    @pytest.mark.asyncio
    async def test_hunt_and_triage_rejected_low_match(self, db_session: AsyncSession) -> None:
        """Valida rejeição por score de aderência inferior à nota de corte do usuário."""
        mock_ai = AsyncMock(spec=AIPort)
        mock_ai.analyze_job.return_value = JobAnalysisResult(
            job_title="Rust Blockchain Core Dev",
            seniority_level="Staff",
            mandatory_requirements=["Rust", "Solana", "Cryptography"],
            desirable_requirements=[],
            keywords=["Rust", "Wasm"],
        )
        mock_source = AsyncMock(spec=JobSourcePort)
        mock_source.fetch_job_posting.return_value = ScrapedJobPosting(
            source_url="https://rust.com/vaga",
            company_name="RustLab",
            job_title="Rust Blockchain Core Dev",
            raw_description="Rust and Cryptography",
            work_model="remote",
        )

        service = JobHunterService(db_session, mock_ai, mock_source)
        user = User(firebase_uid="uid-low-match", email="low@test.com", full_name="LowMatch")
        db_session.add(user)
        await db_session.flush()

        goals = JobHunterGoalConfig(
            source_urls=["https://rust.com/vaga"],
            min_match_score=80.0,
        )

        with patch("app.services.job_hunter_service.ProfileService") as mock_profile_cls:
            mock_profile_cls.return_value.get_full_dossier = AsyncMock(
                return_value={"skills": ["Python", "JavaScript"]}
            )
            resp = await service.hunt_and_triage(user, goals)

        assert resp.rejected_count == 1
        assert resp.results[0].decision == "rejected_low_match"
        assert resp.results[0].match_percentage < 80.0
        assert "abaixo do mínimo" in resp.results[0].reason

    @pytest.mark.asyncio
    async def test_hunt_and_triage_approved_with_auto_pre_apply_true(
        self, db_session: AsyncSession
    ) -> None:
        """Valida aprovação com criação automática de Application, Note e Notification no ATS."""
        mock_ai = AsyncMock(spec=AIPort)
        mock_ai.analyze_job.return_value = JobAnalysisResult(
            job_title="Senior Python Architect",
            seniority_level="Senior",
            mandatory_requirements=["Python", "FastAPI"],
            desirable_requirements=["Docker"],
            keywords=["Python", "FastAPI"],
        )
        mock_source = AsyncMock(spec=JobSourcePort)
        mock_source.fetch_job_posting.return_value = ScrapedJobPosting(
            source_url="https://perfect-match.com/job/42",
            company_name="HighFit Tech",
            job_title="Senior Python Architect",
            raw_description="Python, FastAPI e Docker",
            work_model="remote",
            salary_range="R$ 20.000",
            location="São Paulo, SP",
        )

        service = JobHunterService(db_session, mock_ai, mock_source)
        user = User(
            firebase_uid="uid-approved-auto",
            email="auto@test.com",
            full_name="Auto Applicant",
        )
        db_session.add(user)
        await db_session.flush()

        goals = JobHunterGoalConfig(
            source_urls=["https://perfect-match.com/job/42"],
            min_match_score=50.0,
            auto_pre_apply=True,
        )

        with patch("app.services.job_hunter_service.ProfileService") as mock_profile_cls:
            mock_profile_cls.return_value.get_full_dossier = AsyncMock(
                return_value={
                    "skills": ["Python", "FastAPI", "Docker"],
                    "experiences": [
                        {
                            "company_name": "Old Tech",
                            "position_title": "Python Lead",
                            "tech_stack": ["Python", "FastAPI"],
                            "bullet_points": ["Criou APIs escaláveis"],
                        }
                    ],
                }
            )
            resp = await service.hunt_and_triage(user, goals)

        assert resp.pre_applied_count == 1
        assert resp.processed_count == 1
        assert resp.results[0].decision == "pre_applied"
        assert resp.results[0].application_id is not None
        assert resp.results[0].match_percentage >= 50.0

        # Verifica persistência no banco de dados relacional
        created_app = await db_session.get(Application, resp.results[0].application_id)
        assert created_app is not None
        assert created_app.company_name == "HighFit Tech"
        assert created_app.job_title == "Senior Python Architect"
        assert created_app.job_url == "https://perfect-match.com/job/42"
        assert created_app.status == "saved"
        assert created_app.salary_range == "R$ 20.000"
        assert created_app.location == "São Paulo, SP"
        assert created_app.work_model == "remote"

    @pytest.mark.asyncio
    async def test_hunt_and_triage_approved_with_auto_pre_apply_false(
        self, db_session: AsyncSession
    ) -> None:
        """Valida aprovação com auto_pre_apply=False marcando approved_manual sem persistir ATS."""
        mock_ai = AsyncMock(spec=AIPort)
        mock_ai.analyze_job.return_value = JobAnalysisResult(
            job_title="Senior Python Architect",
            seniority_level="Senior",
            mandatory_requirements=["Python"],
            desirable_requirements=[],
            keywords=["Python"],
        )
        mock_source = AsyncMock(spec=JobSourcePort)
        mock_source.fetch_job_posting.return_value = ScrapedJobPosting(
            source_url="https://manual-review.com/job/10",
            company_name="ManualCorp",
            job_title="Senior Python Architect",
            raw_description="Python",
            work_model="remote",
        )

        service = JobHunterService(db_session, mock_ai, mock_source)
        user = User(
            firebase_uid="uid-approved-manual",
            email="manual@test.com",
            full_name="Manual Reviewer",
        )
        db_session.add(user)
        await db_session.flush()

        goals = JobHunterGoalConfig(
            source_urls=["https://manual-review.com/job/10"],
            min_match_score=50.0,
            auto_pre_apply=False,
        )

        with patch("app.services.job_hunter_service.ProfileService") as mock_profile_cls:
            mock_profile_cls.return_value.get_full_dossier = AsyncMock(
                return_value={"skills": ["Python"]}
            )
            resp = await service.hunt_and_triage(user, goals)

        assert resp.pre_applied_count == 0
        assert resp.processed_count == 1
        assert resp.results[0].decision == "approved_manual"
        assert resp.results[0].application_id is None
        assert "aguardando revisão manual" in resp.results[0].reason


# ============================================================================
# 4. TESTES DA INJEÇÃO DE DEPENDÊNCIA (app.api.v1.deps.get_job_hunter_service)
# ============================================================================


class TestJobHunterDependency:
    """Testes para a factory de injeção de dependência get_job_hunter_service."""

    @pytest.mark.asyncio
    async def test_get_job_hunter_service_factory(self, db_session: AsyncSession) -> None:
        """Valida a resolução e instanciação de JobHunterService via deps.py."""
        user = User(
            firebase_uid="uid-dep-test",
            email="dep@test.com",
            full_name="Dep User",
        )
        user.settings = None  # Evita lazy loading de relacionamento não persistido
        db_session.add(user)
        await db_session.flush()

        service = await get_job_hunter_service(db=db_session, current_user=user)

        assert isinstance(service, JobHunterService)
        assert service.db is db_session
        assert isinstance(service.ai_port, GeminiAIAdapter)
        assert isinstance(service.job_source_port, HttpJobSourceAdapter)


# ============================================================================
# 5. TESTES DOS SCHEMAS PYDANTIC (app.api.v1.schemas.job_hunter)
# ============================================================================


class TestJobHunterSchemas:
    """Testes para validação e limites de fronteira (BVA) dos schemas Pydantic v2."""

    def test_goal_config_defaults_and_validation(self) -> None:
        """Testa valores padrão e limites de validação de JobHunterGoalConfig."""
        config = JobHunterGoalConfig(source_urls=["https://valid.com"])
        assert config.min_match_score == 60.0
        assert config.auto_pre_apply is True
        assert config.target_roles == []
        assert config.excluded_companies == []
        assert config.allowed_work_models == ["remote", "hybrid", "on-site"]

        # source_urls vazio deve falhar
        with pytest.raises(ValidationError):
            JobHunterGoalConfig(source_urls=[])

        # source_urls com mais de 10 itens deve falhar
        with pytest.raises(ValidationError):
            JobHunterGoalConfig(source_urls=[f"https://job{i}.com" for i in range(11)])

        # min_match_score fora dos limites [0, 100]
        with pytest.raises(ValidationError):
            JobHunterGoalConfig(source_urls=["https://v.com"], min_match_score=-1.0)
        with pytest.raises(ValidationError):
            JobHunterGoalConfig(source_urls=["https://v.com"], min_match_score=100.1)

    def test_item_result_and_run_response_schemas(self) -> None:
        """Testa serialização e campos de JobHunterItemResult e JobHunterRunResponse."""
        item = JobHunterItemResult(
            source_url="https://valid.com",
            company_name="Empresa",
            job_title="Cargo",
            work_model="remote",
            match_percentage=75.5,
            decision="pre_applied",
            reason="Aprovada",
            mandatory_requirements=["Python"],
            missing_requirements=[],
            error_code=None,
        )
        assert item.decision == "pre_applied"
        assert item.match_percentage == 75.5

        resp = JobHunterRunResponse(
            total_sources=1,
            processed_count=1,
            pre_applied_count=1,
            rejected_count=0,
            failed_count=0,
            skipped_duplicate_count=0,
            results=[item],
        )
        assert resp.total_sources == 1
        assert resp.results[0].company_name == "Empresa"
