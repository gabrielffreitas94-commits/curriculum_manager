"""Testes unitários e guardrails anti-regressão de segurança para o url_scraper.

Valida a proteção contra SSRF (CWE-918), controle de tamanho contra DoS (CWE-400),
bloqueio de esquemas não-HTTP e extração sanitizada de texto HTML.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.core.url_scraper import (
    PayloadTooLargeError,
    ScraperTimeoutError,
    SSRFProtectionError,
    UrlScraperError,
    _SafeTextHTMLParser,
    extract_clean_text_from_html,
    is_safe_ip,
    safe_fetch_url,
    validate_target_url,
)


class TestSSRFSecurityGuardrails:
    """Suíte de guardrails estritos contra ataques SSRF (CWE-918)."""

    def test_guardrail_blocks_private_and_loopback_ips(self) -> None:
        """VETOR DE AMEAÇA: CWE-918 (Server-Side Request Forgery - SSRF).
        Um atacante submete uma URL apontando para localhost (127.0.0.1, ::1)
        ou redes privadas RFC 1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
        para sondar a rede interna ou acessar serviços locais do backend.

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        A função `is_safe_ip` deve retornar estritamente `False` para qualquer IP
        privado, reservado, loopback, link-local ou de metadados de nuvem.

        RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
        Se um desenvolvedor ou LLM simplificar a verificação de IP para apenas
        conferir '127.0.0.1' ou esquecer de tratar CGNAT (100.64.0.0/10) e IPv6 (::1, fe80::),
        a proteção SSRF será burlada silenciosamente.

        PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
        Todos os IPs da lista negra devem retornar `False` sem exceção.
        """
        dangerous_ips = [
            "127.0.0.1",
            "127.0.1.1",
            "::1",
            "10.0.0.1",
            "10.254.254.254",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.1.1",
            "192.168.0.254",
            "169.254.169.254",  # AWS/GCP metadata
            "169.254.1.1",  # Link-local
            "fe80::1",  # IPv6 link-local
            "fc00::1",  # IPv6 ULA
            "0.0.0.0",
            "::",
            "100.64.0.1",  # CGNAT
            "100.127.255.254",  # CGNAT
            "224.0.0.1",  # Multicast
            "240.0.0.1",  # Reserved
            "invalid-ip-string",
        ]

        for ip in dangerous_ips:
            assert is_safe_ip(ip) is False, f"Falha de segurança: IP '{ip}' deveria ser bloqueado!"

        # IPs públicos legítimos devem ser aceitos
        assert is_safe_ip("8.8.8.8") is True
        assert is_safe_ip("1.1.1.1") is True
        assert is_safe_ip("93.184.216.34") is True

    def test_guardrail_rejects_non_http_schemes(self) -> None:
        """VETOR DE AMEAÇA: CWE-918 / CWE-73 (Protocol Smuggling / SSRF via Schemes).
        Tentativa de acessar o sistema de arquivos local (`file:///etc/passwd`)
        ou protocolos de rede arbitrários (`gopher://`, `ftp://`, `dict://`).

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        A função `validate_target_url` deve rejeitar categoricamente qualquer esquema
        que não seja estritamente 'http' ou 'https', levantando `SSRFProtectionError`.

        RISCO DE REGRESSÃO SILENCIOSA:
        Permitir esquemas arbitrários em bibliotecas como httpx ou urllib pode permitir
        leitura de arquivos locais ou ataques de protocol smuggling.

        PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
        Qualquer esquema fora de http/https deve gerar SSRFProtectionError.
        """
        invalid_urls = [
            "file:///etc/passwd",
            "file:///C:/Windows/System32/drivers/etc/hosts",
            "gopher://127.0.0.1:70",
            "ftp://ftp.example.com",
            "dict://127.0.0.1:11211",
            "javascript:alert(1)",
            "",
            "   ",
        ]
        for url in invalid_urls:
            with pytest.raises(SSRFProtectionError):
                validate_target_url(url)

    @patch("socket.getaddrinfo")
    def test_guardrail_blocks_dns_resolving_to_private_ip(
        self, mock_getaddrinfo: MagicMock
    ) -> None:
        """VETOR DE AMEAÇA: CWE-918 (DNS Rebinding / Malicious Domain resolving to Localhost).
        O atacante usa um domínio público legítimo (ex: 'attacker-controlled.com') que
        resolve para 127.0.0.1 ou 169.254.169.254 via DNS dinâmico.

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        A resolução DNS deve ser inspecionada. Se qualquer IP resolvido for restrito,
        a requisição é bloqueada antes de qualquer conexão HTTP.

        RISCO DE REGRESSÃO SILENCIOSA:
        Confiar apenas no nome do domínio ('example.com') sem inspecionar a resposta DNS
        abre uma brecha crítica para DNS Rebinding.

        PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
        Se o DNS resolver para IP restrito, deve levantar SSRFProtectionError.
        """
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("169.254.169.254", 80))]

        with pytest.raises(SSRFProtectionError) as exc_info:
            validate_target_url("http://cloud-metadata-spoof.com/latest/meta-data")
        assert "Acesso bloqueado" in str(exc_info.value)

    @patch("socket.getaddrinfo")
    def test_validate_target_url_empty_or_failed_dns(self, mock_getaddrinfo: MagicMock) -> None:
        """Testa casos limite de falha de resolução DNS e URL sem hostname."""
        import socket

        with pytest.raises(SSRFProtectionError) as exc:
            validate_target_url("http://")
        assert "Hostname ausente" in str(exc.value)

        mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")
        with pytest.raises(SSRFProtectionError) as exc2:
            validate_target_url("https://non-existent-domain-12345.xyz/job")
        assert "Não foi possível resolver o hostname" in str(exc2.value)

        mock_getaddrinfo.side_effect = None
        mock_getaddrinfo.return_value = []
        with pytest.raises(SSRFProtectionError) as exc3:
            validate_target_url("https://empty-ip-domain.com/job")
        assert "Nenhum endereço IP retornado" in str(exc3.value)


class TestSafeFetchUrlAndHtmlParsing:
    """Testes funcionais e de boundary para safe_fetch_url e extração de HTML."""

    @pytest.mark.asyncio
    async def test_safe_fetch_url_success(self) -> None:
        """Testa o fluxo de sucesso de busca e extração de texto de página web."""
        html_sample = """
        <!DOCTYPE html>
        <html>
        <head><title>Job Title</title><style>.hidden { display: none; }</style></head>
        <body>
            <header><nav><a href="/">Home</a></nav></header>
            <main>
                <h1>Engenheiro de Software Sênior (Python)</h1>
                <p>Buscamos profissional com sólida experiência em FastAPI e PostgreSQL.</p>
                <div>Requisitos:</div>
                <ul>
                    <li>Python 3.12+</li>
                    <li>Arquitetura Hexagonal</li>
                </ul>
            </main>
            <footer><p>Copyright 2026</p></footer>
            <script>console.log("tracker");</script>
        </body>
        </html>
        """

        mock_transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200, text=html_sample, headers={"content-type": "text/html"}
            )
        )

        with patch("app.core.url_scraper.validate_target_url") as mock_validate:
            mock_validate.return_value = ("https", "jobs.example.com", 443)
            async with httpx.AsyncClient(transport=mock_transport) as client:
                text = await safe_fetch_url("https://jobs.example.com/vaga/123", client=client)

        assert "Engenheiro de Software Sênior (Python)" in text
        assert "Buscamos profissional com sólida experiência em FastAPI e PostgreSQL." in text
        assert "Python 3.12+" in text
        assert "Arquitetura Hexagonal" in text
        # Tags descartadas não devem constar no texto final
        assert "tracker" not in text
        assert "Copyright 2026" not in text
        assert "Home" not in text

    @pytest.mark.asyncio
    async def test_safe_fetch_url_payload_too_large(self) -> None:
        """VETOR DE AMEAÇA: CWE-400 (Memory Exhaustion / Uncontrolled Resource Consumption).
        O servidor remoto responde com um fluxo gigantesco de dados para travar o backend.

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        A função `safe_fetch_url` deve interromper o download e levantar `PayloadTooLargeError`
        ao exceder o parâmetro `max_bytes`.
        """
        giant_payload = b"X" * (1024 * 1024 + 10)  # > 1MB

        mock_transport = httpx.MockTransport(
            lambda request: httpx.Response(200, content=giant_payload)
        )

        with patch("app.core.url_scraper.validate_target_url") as mock_validate:
            mock_validate.return_value = ("https", "jobs.example.com", 443)
            async with httpx.AsyncClient(transport=mock_transport) as client:
                with pytest.raises(PayloadTooLargeError):
                    await safe_fetch_url(
                        "https://jobs.example.com/vaga/large",
                        max_bytes=1024 * 1024,
                        client=client,
                    )

    @pytest.mark.asyncio
    async def test_safe_fetch_url_timeout(self) -> None:
        """Testa o tratamento adequado de timeout de requisição."""

        def raise_timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Timeout ao aguardar resposta")

        mock_transport = httpx.MockTransport(raise_timeout)

        with patch("app.core.url_scraper.validate_target_url") as mock_validate:
            mock_validate.return_value = ("https", "jobs.example.com", 443)
            async with httpx.AsyncClient(transport=mock_transport) as client:
                with pytest.raises(ScraperTimeoutError) as exc_info:
                    await safe_fetch_url("https://jobs.example.com/vaga/slow", client=client)
                assert "Tempo limite" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_safe_fetch_url_redirect_handling(self) -> None:
        """Testa o seguimento manual de redirects revalidando IP a cada salto."""

        def handle_redirect(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/old-vaga":
                return httpx.Response(
                    302, headers={"Location": "https://jobs.example.com/new-vaga"}
                )
            return httpx.Response(200, text="<p>Vaga redirecionada com sucesso</p>")

        mock_transport = httpx.MockTransport(handle_redirect)

        with patch("app.core.url_scraper.validate_target_url") as mock_validate:
            mock_validate.return_value = ("https", "jobs.example.com", 443)
            async with httpx.AsyncClient(transport=mock_transport) as client:
                text = await safe_fetch_url("https://jobs.example.com/old-vaga", client=client)
                assert "Vaga redirecionada com sucesso" in text
                assert mock_validate.call_count == 2

    @pytest.mark.asyncio
    async def test_safe_fetch_url_redirect_missing_location(self) -> None:
        """Testa resposta 302 sem header Location."""
        mock_transport = httpx.MockTransport(lambda request: httpx.Response(302, headers={}))
        with patch("app.core.url_scraper.validate_target_url"):
            async with httpx.AsyncClient(transport=mock_transport) as client:
                with pytest.raises(UrlScraperError) as exc:
                    await safe_fetch_url("https://jobs.example.com/redirect-null", client=client)
                assert "sem header Location" in str(exc.value)

    @pytest.mark.asyncio
    async def test_safe_fetch_url_too_many_redirects(self) -> None:
        """
        VETOR DE AMEAÇA: CWE-400 (Uncontrolled Resource Consumption) & CWE-918 (SSRF).
        Servidor malicioso induz 'safe_fetch_url' a seguir sequências infinitas ou cíclicas
        de redirecionamento HTTP (loop 301/302), provocando exaustão de memória e conexões assíncronas.

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        O mecanismo de fetch DEVE contabilizar rigorosamente cada redirecionamento e abortar
        lançando 'SSRFProtectionError' assim que a contagem atingir o limiar 'max_redirects'.

        RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
        Um desenvolvedor ou IA pode substituir o loop controlado por 'follow_redirects=True' nativo
        sem impor validação prévia de IP e limite estrito em cada salto.

        PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
        Tentativa de scraping em endpoint com loop infinito lança 'SSRFProtectionError' ao atingir max_redirects.
        """
        mock_transport = httpx.MockTransport(
            lambda request: httpx.Response(
                302, headers={"Location": "https://jobs.example.com/loop"}
            )
        )
        with patch("app.core.url_scraper.validate_target_url"):
            async with httpx.AsyncClient(transport=mock_transport) as client:
                with pytest.raises(SSRFProtectionError) as exc:
                    await safe_fetch_url(
                        "https://jobs.example.com/loop",
                        max_redirects=2,
                        client=client,
                    )
                assert "Limite máximo de 2 redirecionamentos excedido" in str(exc.value)

    @pytest.mark.asyncio
    async def test_safe_fetch_url_http_error_status(self) -> None:
        """Testa resposta com código de erro HTTP (ex: 404, 500)."""
        mock_transport = httpx.MockTransport(lambda request: httpx.Response(404, text="Not Found"))
        with patch("app.core.url_scraper.validate_target_url"):
            async with httpx.AsyncClient(transport=mock_transport) as client:
                with pytest.raises(UrlScraperError) as exc:
                    await safe_fetch_url("https://jobs.example.com/404", client=client)
                assert "HTTP 404" in str(exc.value)

    @pytest.mark.asyncio
    async def test_safe_fetch_url_transport_error(self) -> None:
        """Testa erro de rede de baixo nível (ConnectError)."""

        def raise_conn_error(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        mock_transport = httpx.MockTransport(raise_conn_error)
        with patch("app.core.url_scraper.validate_target_url"):
            async with httpx.AsyncClient(transport=mock_transport) as client:
                with pytest.raises(UrlScraperError) as exc:
                    await safe_fetch_url("https://jobs.example.com/down", client=client)
                assert "Erro de transporte HTTP" in str(exc.value)

    def test_extract_clean_text_from_html_edge_cases(self) -> None:
        """Testa casos limite de extração HTML (string vazia e corrupção)."""
        assert extract_clean_text_from_html("") == ""
        # HTML sem tags válidas
        assert (
            extract_clean_text_from_html("Apenas texto puro sem marcação.")
            == "Apenas texto puro sem marcação."
        )

        # Simulação de exceção no feed para validar fallback
        with patch.object(
            _SafeTextHTMLParser, "feed", side_effect=RuntimeError("Corrupted stream")
        ):
            result = extract_clean_text_from_html("<malformed>test</malformed>")
            assert result == "<malformed>test</malformed>"

    @patch("socket.getaddrinfo")
    def test_validate_target_url_success(self, mock_getaddrinfo: MagicMock) -> None:
        """Testa retorno bem-sucedido de esquema, hostname e porta para IP público."""
        mock_getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        scheme, host, port = validate_target_url("https://example.com/careers")
        assert scheme == "https"
        assert host == "example.com"
        assert port == 443

    @pytest.mark.asyncio
    async def test_safe_fetch_url_default_client_lifecycle(self) -> None:
        """Testa ciclo de vida com cliente padrão (sem injeção prévia) e fechamento do cliente."""
        html_sample = "<p>Conteúdo de teste default client</p>"
        mock_transport = httpx.MockTransport(lambda request: httpx.Response(200, text=html_sample))

        with patch("app.core.url_scraper.validate_target_url") as mock_validate:
            mock_validate.return_value = ("https", "jobs.example.com", 443)
            with patch(
                "httpx.AsyncClient", return_value=httpx.AsyncClient(transport=mock_transport)
            ):
                text = await safe_fetch_url("https://jobs.example.com/vaga/default-client")
                assert "Conteúdo de teste default client" in text
