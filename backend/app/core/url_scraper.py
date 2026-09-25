"""Utilitário de scraping seguro de URLs de vagas de emprego.

Implementa blindagem rigorosa contra Server-Side Request Forgery (SSRF - CWE-918),
prevenção contra DoS e exaustão de memória por payload excessivo (CWE-400),
resolução prévia de DNS (fail-closed) e extração sanitizada de texto a partir de HTML.
"""

import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# Faixas de IP reservadas / CGNAT para validação estrita
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")
_CLOUD_METADATA_IP = ipaddress.ip_address("169.254.169.254")

# Tags HTML cujo conteúdo textual deve ser completamente descartado
_DISALLOWED_TAGS = frozenset(
    {"script", "style", "noscript", "header", "footer", "nav", "svg", "head", "iframe"}
)


class UrlScraperError(Exception):
    """Exceção base para erros de scraping seguro de URLs."""

    pass


URLScraperError = UrlScraperError


class SSRFProtectionError(UrlScraperError):
    """Lançada quando a URL aponta para endereço privado, loopback ou restrito."""

    pass


class PayloadTooLargeError(UrlScraperError):
    """Lançada quando a resposta HTTP excede o limite máximo de bytes permitido."""

    pass


class ScraperTimeoutError(UrlScraperError):
    """Lançada quando a requisição excede o timeout estipulado."""

    pass


def is_safe_ip(ip_str: str) -> bool:
    """Valida se o endereço IP é público e seguro contra ataques SSRF.

    Bloqueia:
    - Endereços de loopback (127.0.0.0/8, ::1)
    - Redes privadas RFC 1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fc00::/7)
    - Link-local (169.254.0.0/16, fe80::/10)
    - Metadados de nuvem AWS/GCP/Azure (169.254.169.254)
    - Carrier-Grade NAT (100.64.0.0/10)
    - Multicast, não especificados e reservados

    Args:
        ip_str: String representando o endereço IPv4 ou IPv6.

    Returns:
        bool: True se o IP for público e seguro; False se for restrito/inseguro.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False

    return not (ip.version == 4 and ip in _CGNAT_NETWORK)


def validate_target_url(url: str) -> tuple[str, str, int]:
    """Valida sintaxe da URL e resolve seu DNS verificando se todos os IPs são seguros.

    Args:
        url: URL alvo informada pelo usuário.

    Returns:
        tuple[str, str, int]: (esquema, hostname, porta)

    Raises:
        SSRFProtectionError: Se o esquema não for http/https ou o host resolver para IP inseguro.
    """
    if not url or not isinstance(url, str):
        raise SSRFProtectionError("URL inválida ou ausente.")

    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SSRFProtectionError(
            f"Esquema de URL '{scheme}' não suportado. Utilize apenas http ou https."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFProtectionError("Hostname ausente na URL fornecida.")

    port = parsed.port or (443 if scheme == "https" else 80)

    try:
        addr_infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFProtectionError(
            f"Não foi possível resolver o hostname '{hostname}': {exc}"
        ) from exc

    if not addr_infos:
        raise SSRFProtectionError(f"Nenhum endereço IP retornado para '{hostname}'.")

    # Avaliação fail-closed: TODOS os IPs resolvidos devem ser seguros
    for addr_info in addr_infos:
        ip_candidate = str(addr_info[4][0])
        if not is_safe_ip(ip_candidate):
            logger.warning(
                "ssrf_attempt_blocked",
                target_url=url,
                resolved_ip=ip_candidate,
                hostname=hostname,
            )
            raise SSRFProtectionError(
                f"Acesso bloqueado: o destino '{hostname}' resolve para endereço "
                f"restrito ({ip_candidate})."
            )

    return scheme, hostname, port


class _SafeTextHTMLParser(HTMLParser):
    """Parser HTML seguro baseado na biblioteca padrão que extrai texto visível."""

    def __init__(self) -> None:
        super().__init__()
        self._disallowed_depth = 0
        self._text_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _DISALLOWED_TAGS:
            self._disallowed_depth += 1
        elif tag.lower() in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"):
            self._text_chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _DISALLOWED_TAGS and self._disallowed_depth > 0:
            self._disallowed_depth -= 1
        elif tag.lower() in ("p", "div", "li", "tr"):
            self._text_chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._disallowed_depth == 0:
            cleaned = data.strip()
            if cleaned:
                self._text_chunks.append(data)

    def get_text(self) -> str:
        raw_joined = "".join(self._text_chunks)
        # Normalização de quebras de linha e espaçamentos múltiplos
        lines = [line.strip() for line in raw_joined.splitlines() if line.strip()]
        return "\n".join(lines)


def extract_clean_text_from_html(html_content: str) -> str:
    """Extrai o texto visível de um documento HTML removendo scripts e tags irrelevantes.

    Args:
        html_content: String contendo o markup HTML.

    Returns:
        str: Texto limpo estruturado por quebras de linha.
    """
    if not html_content:
        return ""
    parser = _SafeTextHTMLParser()
    try:
        parser.feed(html_content)
        parser.close()
        return parser.get_text()
    except Exception:
        # Fallback defensivo caso o HTML esteja extremamente corrompido
        return html_content.strip()


async def safe_fetch_url(
    url: str,
    max_bytes: int = 2_097_152,  # 2 MB
    timeout_s: float = 8.0,
    max_redirects: int = 3,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Efetua download seguro do conteúdo de uma URL com proteção contra SSRF e DoS.

    Implementa rastreamento manual de redirecionamentos (follow_redirects=False) para
    garantir que nenhum redirect direcione para endereços internos não autorizados.

    Args:
        url: URL completa a ser consultada.
        max_bytes: Limite máximo em bytes do corpo da resposta.
        timeout_s: Tempo limite da requisição em segundos.
        max_redirects: Quantidade máxima permitida de redirecionamentos.
        client: Cliente HTTP opcional para injeção em testes.

    Returns:
        str: Texto limpo extraído da página web.

    Raises:
        SSRFProtectionError: Se a URL ou qualquer redirect apontar para IP restrito.
        PayloadTooLargeError: Se o conteúdo exceder max_bytes.
        ScraperTimeoutError: Se ocorrer timeout.
        UrlScraperError: Em falhas gerais de conexão ou HTTP.
    """
    current_url = url
    redirects_followed = 0

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (ThothCVs Job Ingestion Bot)"
        ),
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
    }

    local_client = client or httpx.AsyncClient(timeout=timeout_s, verify=True)
    should_close_client = client is None

    try:
        while True:
            # 1. Validação estrita de IP antes de cada salto
            validate_target_url(current_url)

            try:
                # Requisição com streaming para validar tamanho em tempo real
                async with local_client.stream(
                    "GET",
                    current_url,
                    headers=headers,
                    follow_redirects=False,
                ) as response:
                    # Trata redirecionamentos manualmente
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("Location")
                        if not location:
                            raise UrlScraperError("Redirecionamento sem header Location.")

                        redirects_followed += 1
                        if redirects_followed > max_redirects:
                            raise SSRFProtectionError(
                                f"Limite máximo de {max_redirects} redirecionamentos excedido."
                            )

                        current_url = urljoin(current_url, location)
                        continue

                    if response.status_code >= 400:
                        raise UrlScraperError(
                            f"Falha ao carregar página: HTTP {response.status_code}."
                        )

                    # Leitura em streaming controlada por max_bytes
                    chunks: list[bytes] = []
                    total_downloaded = 0

                    async for chunk in response.aiter_bytes():
                        total_downloaded += len(chunk)
                        if total_downloaded > max_bytes:
                            raise PayloadTooLargeError(
                                f"Página excede o limite máximo permitido de {max_bytes} bytes."
                            )
                        chunks.append(chunk)

                    raw_body = b"".join(chunks)

                    # Detecção de codificação
                    encoding = response.encoding or "utf-8"
                    html_text = raw_body.decode(encoding, errors="replace")
                    return extract_clean_text_from_html(html_text)

            except httpx.TimeoutException as exc:
                raise ScraperTimeoutError(f"Tempo limite de {timeout_s}s esgotado: {exc}") from exc
            except (
                SSRFProtectionError,
                PayloadTooLargeError,
                ScraperTimeoutError,
                UrlScraperError,
            ):
                raise
            except httpx.HTTPError as exc:
                raise UrlScraperError(f"Erro de transporte HTTP ao acessar a URL: {exc}") from exc

    finally:
        if should_close_client:
            await local_client.aclose()
