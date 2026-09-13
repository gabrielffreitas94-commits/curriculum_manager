"""Adaptador de renderização de currículos no formato Word (.docx).

Utiliza python-docx para construir documentos em coluna única, semanticamente
estruturados e estritamente otimizados para ATS (Applicant Tracking Systems),
sem o uso de tabelas complexas, caixas de texto ou cabeçalhos flutuantes.
"""

import time
from io import BytesIO
from typing import Any

from docx import Document
from docx.document import Document as DocxDocument
from docx.shared import Inches, Pt, RGBColor

from app.core.i18n import LocaleRegistry
from app.core.logging import get_logger

logger = get_logger(__name__)


class DocxAdapter:
    """Adaptador de renderização DOCX com tipografia e diagramação ATS-friendly."""

    def render_docx(self, resume_data: dict[str, Any], locale_code: str = "pt-BR") -> bytes:
        """Gera um arquivo DOCX determinístico a partir do payload estruturado do currículo.

        Args:
            resume_data: Dicionário contendo os nós do currículo sintetizado.
            locale_code: Código do idioma para tradução de seções e datas.

        Returns:
            Bytes correspondentes ao arquivo OpenXML .docx.
        """
        start_time = time.perf_counter()
        doc = Document()

        # Configuração de Margens (1.5 cm / ~0.6 pol)
        for section in doc.sections:
            section.top_margin = Inches(0.6)
            section.bottom_margin = Inches(0.6)
            section.left_margin = Inches(0.7)
            section.right_margin = Inches(0.7)

        # 1. Cabeçalho / Identificação
        header = resume_data.get("header", {})
        full_name = header.get("full_name", "")
        target_title = header.get("target_title", "")
        email = header.get("email", "")
        phone = header.get("phone", "")
        location = header.get("location", "")
        links = header.get("links", {})

        p_name = doc.add_paragraph()
        run_name = p_name.add_run(full_name)
        run_name.bold = True
        run_name.font.size = Pt(18)
        run_name.font.color.rgb = RGBColor(30, 41, 59)
        p_name.paragraph_format.space_after = Pt(2)

        if target_title:
            p_title = doc.add_paragraph()
            run_title = p_title.add_run(target_title)
            run_title.bold = True
            run_title.font.size = Pt(12)
            run_title.font.color.rgb = RGBColor(71, 85, 105)
            p_title.paragraph_format.space_after = Pt(4)

        # Linha de Contato
        contact_parts = [part for part in [email, phone, location] if part]
        if isinstance(links, dict):
            for link_val in links.values():
                if link_val:
                    contact_parts.append(str(link_val))

        if contact_parts:
            p_contact = doc.add_paragraph()
            p_contact.paragraph_format.space_after = Pt(12)
            run_contact = p_contact.add_run(" | ".join(contact_parts))
            run_contact.font.size = Pt(9.5)
            run_contact.font.color.rgb = RGBColor(100, 116, 139)

        # 2. Resumo Profissional
        summary = resume_data.get("professional_summary", "")
        if summary:
            self._add_section_heading(doc, LocaleRegistry.get_translation(locale_code, "summary"))
            p_sum = doc.add_paragraph(summary)
            p_sum.paragraph_format.space_after = Pt(10)
            p_sum.runs[0].font.size = Pt(10)

        # 3. Experiência Profissional
        experiences = resume_data.get("selected_experiences", [])
        if experiences:
            self._add_section_heading(
                doc, LocaleRegistry.get_translation(locale_code, "experience")
            )
            for exp in experiences:
                comp = exp.get("company_name", "")
                role = exp.get("position_title", "")
                start = LocaleRegistry.format_date(exp.get("start_date"), locale_code)
                end = LocaleRegistry.format_date(
                    exp.get("end_date"),
                    locale_code,
                    is_current=exp.get("is_current", False),
                )
                date_range = f"{start} - {end}" if start and end else (start or end or "")

                p_exp = doc.add_paragraph()
                p_exp.paragraph_format.space_after = Pt(2)
                p_exp.paragraph_format.space_before = Pt(4)

                run_role = p_exp.add_run(f"{role} | ")
                run_role.bold = True
                run_role.font.size = Pt(10.5)

                run_comp = p_exp.add_run(comp)
                run_comp.font.size = Pt(10.5)

                if date_range:
                    run_date = p_exp.add_run(f" ({date_range})")
                    run_date.italic = True
                    run_date.font.size = Pt(9.5)
                    run_date.font.color.rgb = RGBColor(100, 116, 139)

                for bullet in exp.get("bullet_points", []):
                    p_bullet = doc.add_paragraph(bullet, style="List Bullet")
                    p_bullet.paragraph_format.space_after = Pt(2)
                    p_bullet.runs[0].font.size = Pt(9.5)

                tech_stack = exp.get("tech_stack", [])
                if tech_stack:
                    p_tech = doc.add_paragraph()
                    p_tech.paragraph_format.space_after = Pt(6)
                    run_label = p_tech.add_run("Tecnologias: ")
                    run_label.bold = True
                    run_label.font.size = Pt(9)
                    run_vals = p_tech.add_run(", ".join(tech_stack))
                    run_vals.font.size = Pt(9)

        # 4. Habilidades e Tecnologias
        skills = resume_data.get("skills_highlighted", [])
        if skills:
            self._add_section_heading(doc, LocaleRegistry.get_translation(locale_code, "skills"))
            p_sk = doc.add_paragraph(", ".join(skills))
            p_sk.paragraph_format.space_after = Pt(10)
            p_sk.runs[0].font.size = Pt(9.5)

        # 5. Formação Acadêmica
        education = resume_data.get("education", [])
        if education:
            self._add_section_heading(doc, LocaleRegistry.get_translation(locale_code, "education"))
            for edu in education:
                deg = edu.get("degree", "")
                inst = edu.get("institution", "")
                start = LocaleRegistry.format_date(edu.get("start_date"), locale_code)
                end = LocaleRegistry.format_date(edu.get("end_date"), locale_code)
                date_range = f" ({start} - {end})" if start and end else ""

                p_edu = doc.add_paragraph()
                p_edu.paragraph_format.space_after = Pt(3)
                run_deg = p_edu.add_run(deg)
                run_deg.bold = True
                run_deg.font.size = Pt(10)
                if inst:
                    run_inst = p_edu.add_run(f" - {inst}")
                    run_inst.font.size = Pt(10)
                if date_range:
                    run_dr = p_edu.add_run(date_range)
                    run_dr.italic = True
                    run_dr.font.size = Pt(9)

        # 6. Certificações
        certifications = resume_data.get("certifications", [])
        if certifications:
            self._add_section_heading(
                doc, LocaleRegistry.get_translation(locale_code, "certifications")
            )
            for cert in certifications:
                name = cert.get("name", "")
                issuer = cert.get("issuer", "")
                p_cert = doc.add_paragraph(style="List Bullet")
                p_cert.paragraph_format.space_after = Pt(2)
                run_cn = p_cert.add_run(name)
                run_cn.bold = True
                run_cn.font.size = Pt(9.5)
                if issuer:
                    run_ci = p_cert.add_run(f" ({issuer})")
                    run_ci.font.size = Pt(9.5)

        # 7. Idiomas
        languages = resume_data.get("languages", [])
        if languages:
            self._add_section_heading(doc, LocaleRegistry.get_translation(locale_code, "languages"))
            lang_items = [
                f"{lang.get('language')}: {lang.get('proficiency')}"
                if lang.get("proficiency")
                else lang.get("language", "")
                for lang in languages
            ]
            p_lang = doc.add_paragraph(" | ".join(lang_items))
            p_lang.paragraph_format.space_after = Pt(8)
            p_lang.runs[0].font.size = Pt(9.5)

        output_stream = BytesIO()
        doc.save(output_stream)
        docx_bytes = output_stream.getvalue()
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "docx_rendered_successfully",
            document_type="docx",
            docx_size_bytes=len(docx_bytes),
            duration_ms=duration_ms,
            locale_code=locale_code,
        )
        return docx_bytes

    def _add_section_heading(self, doc: DocxDocument, title: str) -> None:
        """Adiciona um cabeçalho de seção padronizado com separador visual ATS.

        Args:
            doc: Instância do Documento python-docx.
            title: Título da seção traduzido.
        """
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(title.upper())
        run.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = RGBColor(30, 41, 59)
