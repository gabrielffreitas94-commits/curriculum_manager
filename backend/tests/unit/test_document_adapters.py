"""Testes unitários dos adaptadores de documentos (DocxAdapter e WeasyPrintAdapter).

Valida a conformidade com a skill weasyprint-pdf-generator, gerando documentos
com formatação ATS determinística, quebras de página controladas e suporte multilíngue.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.adapters.docx_adapter import DocxAdapter
from app.adapters.weasyprint_adapter import WeasyPrintAdapter, blocked_url_fetcher


@pytest.fixture
def sample_resume_data() -> dict:
    """Fixture com payload estruturado de currículo para teste de renderização."""
    return {
        "header": {
            "full_name": "Maria Silva",
            "target_title": "Engenheira de Software Senior",
            "email": "maria.silva@exemplo.com",
            "phone": "+55 11 98888-7777",
            "location": "São Paulo, SP - Brasil",
            "links": {"linkedin": "https://linkedin.com/in/mariasilva"},
        },
        "professional_summary": (
            "Engenheira de software com 8 anos de experiência em microsserviços Python e Cloud."
        ),
        "selected_experiences": [
            {
                "company_name": "Tech Corp",
                "position_title": "Tech Lead",
                "start_date": "2021-03-01",
                "end_date": None,
                "is_current": True,
                "bullet_points": [
                    "Liderou 6 engenheiros na migração para arquitetura orientada a eventos.",
                    "Reduziu custos de infraestrutura em 35% com otimização no GCP.",
                ],
                "tech_stack": ["Python", "FastAPI", "GCP", "PostgreSQL"],
            }
        ],
        "skills_highlighted": ["Python", "FastAPI", "Docker", "GCP", "Kubernetes"],
        "education": [
            {
                "degree": "Bacharelado em Ciência da Computação",
                "institution": "Universidade de São Paulo",
                "start_date": "2013-02-01",
                "end_date": "2017-12-01",
            }
        ],
        "certifications": [
            {
                "name": "Google Cloud Professional Cloud Architect",
                "issuer": "Google",
                "issue_date": "2022-08-01",
            }
        ],
        "languages": [
            {"language": "Português", "proficiency": "Nativo"},
            {"language": "Inglês", "proficiency": "Avançado / C1"},
        ],
    }


def test_docx_adapter_render_valid_bytes(sample_resume_data: dict) -> None:
    """Valida a renderização de arquivo DOCX compatível com ATS."""
    adapter = DocxAdapter()
    docx_bytes = adapter.render_docx(sample_resume_data, locale_code="pt-BR")

    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 0
    # Valida assinatura 'PK\x03\x04' de arquivo ZIP / DOCX OpenXML
    assert docx_bytes.startswith(b"PK\x03\x04")


def test_docx_adapter_english_locale(sample_resume_data: dict) -> None:
    """Valida a renderização de DOCX no idioma inglês (en-US)."""
    adapter = DocxAdapter()
    docx_bytes = adapter.render_docx(sample_resume_data, locale_code="en-US")

    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 0
    assert docx_bytes.startswith(b"PK\x03\x04")


def test_weasyprint_adapter_renders_pdf() -> None:
    """Valida que o adaptador WeasyPrint chama a biblioteca e retorna os bytes do PDF."""
    adapter = WeasyPrintAdapter()
    dummy_html = "<html><body><h1>Currículo ATS</h1></body></html>"

    mock_wp = MagicMock()
    mock_html_instance = MagicMock()
    mock_html_instance.write_pdf.return_value = b"%PDF-1.4 mock pdf content"
    mock_wp.HTML.return_value = mock_html_instance

    with patch.dict("sys.modules", {"weasyprint": mock_wp}):
        pdf_bytes = adapter.render_pdf(dummy_html)
        assert pdf_bytes.startswith(b"%PDF-1.4")
        mock_wp.HTML.assert_called_once_with(
            string=dummy_html,
            url_fetcher=blocked_url_fetcher,
        )


def test_weasyprint_adapter_raises_when_missing_deps() -> None:
    """Valida mensagem amigável e clara caso as dependências nativas C estejam ausentes."""
    adapter = WeasyPrintAdapter()
    dummy_html = "<html><body><h1>Currículo ATS</h1></body></html>"

    with (
        patch.dict("sys.modules", {"weasyprint": None}),
        pytest.raises(RuntimeError, match="requer bibliotecas C nativas"),
    ):
        adapter.render_pdf(dummy_html)


def test_blocked_url_fetcher_prevents_ssrf_and_lfi() -> None:
    """Garante que o blocked_url_fetcher bloqueie tentativas de SSRF e LFI.

    VETOR DE AMEAÇA:
    - OWASP A10:2021 (SSRF / CWE-918) & OWASP A03:2021 (LFI / CWE-22).
    - Impacto: Tentativas de leitura de metadados da nuvem (169.254.169.254) ou arquivos do host.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O interceptor DEVE levantar ValueError incondicionalmente para qualquer URI externo ou local.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Desenvolvedores ou agentes de IA poderiam tentar criar uma "whitelist" por regex ou liberar
      certos esquemas, introduzindo vulnerabilidades de DNS Rebinding ou redirecionamentos 302.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Valida o bloqueio estrito contra vetores file:// e http:// e assere a mensagem de erro.
    """
    from app.adapters.weasyprint_adapter import blocked_url_fetcher

    # Teste de tentativa de LFI via file://
    with pytest.raises(ValueError, match="Acesso bloqueado por segurança"):
        blocked_url_fetcher("file:///etc/passwd")

    # Teste de tentativa de SSRF contra metadados de nuvem
    with pytest.raises(ValueError, match="Acesso bloqueado por segurança"):
        blocked_url_fetcher("http://169.254.169.254/computeMetadata/v1/")


def test_weasyprint_adapter_custom_url_fetcher() -> None:
    """Valida suporte a injeção de url_fetcher customizado no WeasyPrintAdapter."""
    # 1. Arrange (Preparação)
    custom_fetcher = MagicMock()
    adapter = WeasyPrintAdapter(url_fetcher=custom_fetcher)
    assert adapter._url_fetcher == custom_fetcher

    mock_wp = MagicMock()
    mock_html_instance = MagicMock()
    mock_html_instance.write_pdf.return_value = b"%PDF-1.4 custom"
    mock_wp.HTML.return_value = mock_html_instance

    with patch.dict("sys.modules", {"weasyprint": mock_wp}):
        # 2. Act (Execução)
        pdf_bytes = adapter.render_pdf("<p>Test</p>")

        # 3. Assert - Estado: valida o retorno do método render_pdf
        assert pdf_bytes == b"%PDF-1.4 custom"

        # 3. Assert - Comportamento: verifica se o adaptador realmente repassou o
        # custom_fetcher para a engine do WeasyPrint (evitando uso silencioso do fetcher inseguro)
        mock_wp.HTML.assert_called_once_with(
            string="<p>Test</p>",
            url_fetcher=custom_fetcher,
        )


def test_weasyprint_adapter_never_uses_default_url_fetcher() -> None:
    """Garante que a inicialização padrão NUNCA recorra ao default_url_fetcher do WeasyPrint.

    VETOR DE AMEAÇA:
    - OWASP A10:2021 (SSRF / CWE-918) & OWASP A03:2021 (LFI / CWE-22).
    - Impacto: Acesso a credenciais de nuvem (169.254.169.254) ou segredos (/etc/passwd, .env).

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O adaptador padrão DEVE inicializar com o interceptor blocked_url_fetcher.
    - Qualquer tentativa de renderização com url_fetcher ausente ou default é proibida.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - O WeasyPrint ativa silenciosamente o weasyprint.default_url_fetcher quando url_fetcher é None.
    - Um desenvolvedor ou agente IA poderia supor que url_fetcher=None desativa requisições,
      quando na realidade ativa o comportamento oposto (permite requisições de rede irrestritas).

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Compara diretamente com a referência da função blocked_url_fetcher e rejeita
      explicitamente mock_wp.default_url_fetcher e None.
    """
    adapter = WeasyPrintAdapter()

    # 1. Garante que por padrão o fetcher é estritamente o blocked_url_fetcher
    assert adapter._url_fetcher is blocked_url_fetcher
    assert adapter._url_fetcher is not None

    # 2. Garante que o weasyprint.HTML recebe explicitamente o blocked_url_fetcher
    mock_wp = MagicMock()
    mock_wp.default_url_fetcher = MagicMock(name="default_url_fetcher")
    mock_html_instance = MagicMock()
    mock_html_instance.write_pdf.return_value = b"%PDF-1.4 Guardrail"
    mock_wp.HTML.return_value = mock_html_instance

    with patch.dict("sys.modules", {"weasyprint": mock_wp}):
        adapter.render_pdf("<p>ATS Test</p>")

        # Assegura que o parâmetro passado NUNCA foi o default inseguro e NUNCA foi None
        mock_wp.HTML.assert_called_once_with(
            string="<p>ATS Test</p>",
            url_fetcher=blocked_url_fetcher,
        )
        assert mock_wp.HTML.call_args.kwargs["url_fetcher"] is not mock_wp.default_url_fetcher
        assert mock_wp.HTML.call_args.kwargs["url_fetcher"] is not None
