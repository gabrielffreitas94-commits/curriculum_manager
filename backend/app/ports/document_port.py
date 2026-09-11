"""Porta de abstração hexagonal para renderização de documentos (PDF e DOCX).

Define os contratos estritos de geração de arquivos determinísticos
compatíveis com ATS e padrões internacionais de formatação de currículos.
"""

from abc import ABC, abstractmethod
from typing import Any


class DocumentPort(ABC):
    """Interface abstrata para exportação determinística de currículos."""

    @abstractmethod
    def render_pdf(self, html_content: str) -> bytes:
        """Renderiza uma string HTML estruturada com CSS paged-media em bytes de PDF.

        Args:
            html_content: Código HTML semanticamente estruturado.

        Returns:
            Fluxo binário de bytes correspondente ao arquivo PDF gerado.

        Raises:
            RuntimeError: Caso o renderizador não esteja disponível no ambiente.
        """
        pass

    @abstractmethod
    def render_docx(self, resume_data: dict[str, Any], locale_code: str = "pt-BR") -> bytes:
        """Converte o payload estruturado em um documento Word (.docx) compatível com ATS.

        Args:
            resume_data: Dicionário contendo todas as seções aprovadas no dossiê.
            locale_code: Código do idioma de redação para formatação de títulos e datas.

        Returns:
            Bytes brutos do arquivo .docx gerado.
        """
        pass
