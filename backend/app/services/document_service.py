"""Serviço de orquestração de renderização e exportação de documentos.

Coordena a geração de arquivos PDF e DOCX a partir de snapshots de currículos
persistidos no banco de dados, assegurando o isolamento de tenant, internacionalização
e aplicação de filtros semânticos Jinja2.
"""

import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.docx_adapter import DocxAdapter
from app.adapters.weasyprint_adapter import WeasyPrintAdapter
from app.core.i18n import LocaleRegistry
from app.domain.models import GeneratedResume, User


class DocumentService:
    """Orquestrador de exportação de currículos para formatos PDF e DOCX.

    Attributes:
        db: Sessão assíncrona do SQLAlchemy.
        weasyprint_adapter: Adaptador de renderização HTML para PDF.
        docx_adapter: Adaptador de renderização OpenXML DOCX.
        jinja_env: Ambiente configurado do Jinja2 para templates HTML.
    """

    def __init__(
        self,
        db: AsyncSession,
        weasyprint_adapter: WeasyPrintAdapter | None = None,
        docx_adapter: DocxAdapter | None = None,
    ) -> None:
        """Inicializa o serviço de documentos configurando adaptadores e templates.

        Args:
            db: Sessão de banco de dados ativa.
            weasyprint_adapter: Instância do renderizador de PDF.
            docx_adapter: Instância do renderizador de DOCX.
        """
        self.db = db
        self.weasyprint_adapter = weasyprint_adapter or WeasyPrintAdapter()
        self.docx_adapter = docx_adapter or DocxAdapter()

        templates_dir = Path(__file__).parent.parent / "templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self.jinja_env.filters["format_date"] = LocaleRegistry.format_date

    async def _get_user_resume(
        self,
        resume_id: uuid.UUID,
        user: User,
    ) -> GeneratedResume:
        """Busca o currículo persistido garantindo a barreira multi-tenant do usuário.

        Args:
            resume_id: Identificador universal do currículo.
            user: Usuário solicitante autenticado.

        Returns:
            Entidade GeneratedResume correspondente.

        Raises:
            HTTPException: 404 caso o currículo não exista ou não pertença ao usuário.
        """
        stmt = select(GeneratedResume).where(
            GeneratedResume.id == resume_id,
            GeneratedResume.user_id == user.id,
        )
        result = await self.db.execute(stmt)
        resume = result.scalar_one_or_none()

        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Currículo não encontrado ou não pertence ao usuário solicitante.",
            )

        return resume

    async def export_pdf(
        self,
        resume_id: uuid.UUID,
        user: User,
    ) -> tuple[bytes, str]:
        """Gera e exporta o binário do currículo no formato PDF.

        Args:
            resume_id: UUID do currículo gerado.
            user: Usuário autenticado proprietário.

        Returns:
            Tupla contendo (bytes_do_pdf, nome_do_arquivo).
        """
        resume = await self._get_user_resume(resume_id, user)
        content: dict[str, Any] = resume.structured_content
        locale_code = resume.language or "pt-BR"

        template = self.jinja_env.get_template("resume_ats.html.jinja2")
        html_rendered = template.render(
            locale=locale_code,
            header=content.get("header", {}),
            professional_summary=content.get("professional_summary", ""),
            selected_experiences=content.get("selected_experiences", []),
            skills_highlighted=content.get("skills_highlighted", []),
            education=content.get("education", []),
            certifications=content.get("certifications", []),
            languages=content.get("languages", []),
            t=lambda key: LocaleRegistry.get_translation(locale_code, key),
            t_present=LocaleRegistry.get(locale_code).present_label,
        )

        pdf_bytes = self.weasyprint_adapter.render_pdf(html_rendered)
        filename = f"curriculo_{resume.id}.pdf"
        return pdf_bytes, filename

    async def export_docx(
        self,
        resume_id: uuid.UUID,
        user: User,
    ) -> tuple[bytes, str]:
        """Gera e exporta o binário do currículo no formato Word (.docx).

        Args:
            resume_id: UUID do currículo gerado.
            user: Usuário autenticado proprietário.

        Returns:
            Tupla contendo (bytes_do_docx, nome_do_arquivo).
        """
        resume = await self._get_user_resume(resume_id, user)
        docx_bytes = self.docx_adapter.render_docx(
            resume_data=resume.structured_content,
            locale_code=resume.language or "pt-BR",
        )
        filename = f"curriculo_{resume.id}.docx"
        return docx_bytes, filename
