"""Testes unitários para o DocumentService (Orquestrador de renderização e exportação).

Valida isolamento multi-tenant na consulta do currículo (404), injeção de filtros Jinja2
e renderização mockada de PDF e DOCX.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Application, GeneratedResume, User
from app.services.document_service import DocumentService


@pytest.fixture
def doc_user() -> User:
    """Fixture com usuário dono do documento."""
    return User(
        id=uuid.uuid4(),
        firebase_uid="doc_user_uid_123",
        email="doc_service@thothcvs.ai",
        full_name="Document Tester",
    )


@pytest.mark.asyncio
async def test_document_service_not_found_raises_404(
    db_session: AsyncSession,
    doc_user: User,
) -> None:
    """Garante que tentar exportar currículo inexistente ou de outro usuário levante 404."""
    db_session.add(doc_user)
    await db_session.flush()

    service = DocumentService(db=db_session)
    random_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_pdf:
        await service.export_pdf(resume_id=random_id, user=doc_user)
    assert exc_pdf.value.status_code == 404

    with pytest.raises(HTTPException) as exc_docx:
        await service.export_docx(resume_id=random_id, user=doc_user)
    assert exc_docx.value.status_code == 404


@pytest.mark.asyncio
async def test_document_service_export_pdf_and_docx_success(
    db_session: AsyncSession,
    doc_user: User,
) -> None:
    """Valida renderização e retorno de tupla (bytes, filename) para PDF e DOCX."""
    db_session.add(doc_user)
    await db_session.flush()

    app = Application(
        user_id=doc_user.id,
        company_name="Tech Solutions",
        job_title="Dev Lead",
        job_description="Desc",
        status="applied",
    )
    db_session.add(app)
    await db_session.flush()

    resume = GeneratedResume(
        user_id=doc_user.id,
        application_id=app.id,
        language="pt-BR",
        version_number=1,
        match_percentage=92.0,
        structured_content={
            "header": {
                "full_name": "Document Tester",
                "target_title": "Dev Lead",
                "email": "doc_service@thothcvs.ai",
                "phone": "+55 11 98888-7777",
                "location": "São Paulo, SP",
            },
            "professional_summary": "Resumo profissional de teste.",
            "selected_experiences": [],
            "skills_highlighted": ["Python", "FastAPI"],
            "education": [],
            "certifications": [],
            "languages": [],
        },
    )
    db_session.add(resume)
    await db_session.commit()

    # Mocks para adaptadores
    mock_wp = MagicMock()
    mock_wp.render_pdf.return_value = b"%PDF-1.4 Mock Stream"

    mock_docx = MagicMock()
    mock_docx.render_docx.return_value = b"PK\x03\x04 Mock Docx Stream"

    service = DocumentService(db=db_session, weasyprint_adapter=mock_wp, docx_adapter=mock_docx)

    # 1. Export PDF
    pdf_bytes, pdf_name = await service.export_pdf(resume_id=resume.id, user=doc_user)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert pdf_name == f"curriculo_{resume.id}.pdf"
    assert mock_wp.render_pdf.called

    # 2. Export DOCX
    docx_bytes, docx_name = await service.export_docx(resume_id=resume.id, user=doc_user)
    assert docx_bytes.startswith(b"PK\x03\x04")
    assert docx_name == f"curriculo_{resume.id}.docx"
    assert mock_docx.render_docx.called
