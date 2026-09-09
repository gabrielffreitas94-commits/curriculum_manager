"""Adaptador de renderização de PDF via WeasyPrint com suporte a CSS Paged Media.

Em conformidade com a skill weasyprint-pdf-generator, executa a renderização
HTML para PDF com isolamento de dependências e tratamento de ambiente.
"""

from typing import Any


class WeasyPrintAdapter:
    """Adaptador que converte strings HTML estruturadas em PDFs de alta fidelidade vetorial."""

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
        try:
            import weasyprint
        except (ImportError, OSError) as exc:
            raise RuntimeError(
                "O motor de renderização WeasyPrint requer bibliotecas C nativas "
                "(libgobject, pango, cairo) instaladas no sistema operacional: "
                f"{exc}"
            ) from exc

        html_renderer: Any = weasyprint.HTML(string=html_content)
        pdf_bytes: bytes = html_renderer.write_pdf()
        return pdf_bytes
