"""Adaptador de renderização de PDF via WeasyPrint com suporte a CSS Paged Media.

Em conformidade com a skill weasyprint-pdf-generator, executa a renderização
HTML para PDF com isolamento de dependências, tratamento de ambiente e proteção
estrita contra SSRF e LFI através de um url_fetcher bloqueante.
"""

import time
from collections.abc import Callable
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def blocked_url_fetcher(url: str, timeout: int = 10, ssl_context: Any = None) -> dict[str, Any]:
    """Interceptor que bloqueia requisições de rede externas e arquivos locais.

    Previne vulnerabilidades de Server-Side Request Forgery (SSRF) contra serviços internos
    ou de metadados da nuvem (ex: 169.254.169.254) e Local File Inclusion (LFI via file://).

    Raises:
        ValueError: Sempre que qualquer tentativa de carregar recurso remoto ou local ocorrer.
    """
    raise ValueError(
        f"Acesso bloqueado por segurança: carregamento de recursos externos ou locais "
        f"('{url}') não é permitido durante a renderização do currículo ATS."
    )


class WeasyPrintAdapter:
    """Adaptador que converte strings HTML estruturadas em PDFs de alta fidelidade vetorial."""

    def __init__(
        self,
        url_fetcher: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        """Inicializa o adaptador configurando o interceptor seguro de URLs.

        Args:
            url_fetcher: Função opcional para resolução de recursos. Por padrão,
                utiliza `blocked_url_fetcher` para máxima segurança contra SSRF/LFI.
        """
        self._url_fetcher = url_fetcher or blocked_url_fetcher

    def render_pdf(self, html_content: str) -> bytes:
        """Renderiza o conteúdo HTML em um binário PDF utilizando a engine WeasyPrint.

        Args:
            html_content: Código HTML semanticamente montado com regras de CSS @page.

        Returns:
            Bytes correspondentes ao arquivo PDF compilado.

        Raises:
            RuntimeError: Caso as bibliotecas de sistema C (GTK/Pango/GObject)
                ou o pacote WeasyPrint não estejam disponíveis no sistema operacional.
        """
        start_time = time.perf_counter()
        try:
            import weasyprint
        except (ImportError, OSError) as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "pdf_render_dependencies_missing",
                document_type="pdf",
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise RuntimeError(
                "O motor de renderização WeasyPrint requer bibliotecas C nativas "
                "(libgobject, pango, cairo) instaladas no sistema operacional: "
                f"{exc}"
            ) from exc

        html_renderer: Any = weasyprint.HTML(
            string=html_content,
            url_fetcher=self._url_fetcher,
        )
        pdf_bytes: bytes = html_renderer.write_pdf()
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "pdf_rendered_successfully",
            document_type="pdf",
            pdf_size_bytes=len(pdf_bytes),
            duration_ms=duration_ms,
        )
        return pdf_bytes
