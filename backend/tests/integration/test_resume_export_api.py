"""Testes de integração para os endpoints de exportação de currículos (/export/pdf e /export/docx).

Garante o isolamento multi-tenant (User B não pode exportar documento de User A),
validação de formatos, headers HTTP de download e integridade do streaming.
"""

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    Application,
    GeneratedResume,
    User,
)
from app.ports.auth_port import AuthUser

USER_A_ID = uuid.uuid4()
USER_B_ID = uuid.uuid4()

AUTH_A = AuthUser(
    uid="user_export_a",
    email="user_export_a@example.com",
    full_name="Export User A",
)

AUTH_B = AuthUser(
    uid="user_export_b",
    email="user_export_b@example.com",
    full_name="Export User B",
)


@pytest.fixture
async def setup_resumes(db_session: AsyncSession) -> dict:
    """Configura usuários e currículo persistido para teste de exportação."""
    user_a = User(
        id=USER_A_ID,
        firebase_uid="user_export_a",
        email="user_export_a@example.com",
        full_name="User Export A",
    )
    user_b = User(
        id=USER_B_ID,
        firebase_uid="user_export_b",
        email="user_export_b@example.com",
        full_name="User Export B",
    )
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    app_a = Application(
        id=uuid.uuid4(),
        user_id=user_a.id,
        company_name="Alpha Tech",
        job_title="Lead Architect",
        job_description="Descrição da vaga de Lead Architect.",
        status="applied",
    )
    db_session.add(app_a)
    await db_session.flush()

    resume_a = GeneratedResume(
        id=uuid.uuid4(),
        user_id=user_a.id,
        application_id=app_a.id,
        language="pt-BR",
        version_number=1,
        match_percentage=90.0,
        structured_content={
            "header": {
                "full_name": "User Export A",
                "target_title": "Lead Architect",
                "email": "user_export_a@example.com",
                "phone": "+55 11 99999-0000",
                "location": "São Paulo, SP",
                "links": {},
            },
            "professional_summary": "Arquiteto experiente em sistemas distribuídos.",
            "selected_experiences": [
                {
                    "company_name": "Alpha Tech",
                    "position_title": "Lead Architect",
                    "start_date": "2020-01-01",
                    "end_date": None,
                    "is_current": True,
                    "bullet_points": ["Arquitetou microsserviços escaláveis."],
                    "tech_stack": ["Python", "FastAPI", "PostgreSQL"],
                }
            ],
            "skills_highlighted": ["Python", "FastAPI", "Docker"],
            "education": [],
            "certifications": [],
            "languages": [],
        },
    )
    db_session.add(resume_a)
    await db_session.commit()

    return {
        "resume_id": str(resume_a.id),
        "headers_a": {"Authorization": "Bearer token_a"},
        "headers_b": {"Authorization": "Bearer token_b"},
    }


@pytest.mark.asyncio
async def test_export_docx_success(
    async_client: AsyncClient,
    setup_resumes: dict,
) -> None:
    """Garante que o proprietário consiga exportar seu currículo no formato DOCX."""
    resume_id = setup_resumes["resume_id"]
    headers = setup_resumes["headers_a"]

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_A):
        res = await async_client.get(
            f"/api/v1/resumes/{resume_id}/export/docx",
            headers=headers,
        )
        assert res.status_code == 200
        assert (
            res.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert f'filename="curriculo_{resume_id}.docx"' in res.headers["content-disposition"]
        assert res.content.startswith(b"PK\x03\x04")


@pytest.mark.asyncio
async def test_export_pdf_success(
    async_client: AsyncClient,
    setup_resumes: dict,
) -> None:
    """Garante que o proprietário consiga exportar seu currículo no formato PDF."""
    resume_id = setup_resumes["resume_id"]
    headers = setup_resumes["headers_a"]

    mock_pdf = b"%PDF-1.4 mock stream content"
    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_A),
        patch(
            "app.services.document_service.WeasyPrintAdapter.render_pdf",
            return_value=mock_pdf,
        ),
    ):
        res = await async_client.get(
            f"/api/v1/resumes/{resume_id}/export/pdf",
            headers=headers,
        )
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert f'filename="curriculo_{resume_id}.pdf"' in res.headers["content-disposition"]
        assert res.content.startswith(b"%PDF-1.4")


@pytest.mark.asyncio
async def test_export_tenant_isolation(
    async_client: AsyncClient,
    setup_resumes: dict,
) -> None:
    """
    VETOR DE AMEAÇA: CWE-639 / CWE-284 & OWASP API1:2023 (Broken Object Level Authorization / IDOR).
    Um usuário malicioso ou não autorizado (User B) tenta baixar/exportar os dados de currículo
    privados (PII, histórico, dados de contato) pertencentes a outro candidato (User A).

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    O sistema DEVE responder com HTTP 404 (Not Found) em qualquer tentativa de exportação (DOCX ou PDF)
    sobre um identificador de currículo pertencente a outro usuário, impedindo vazamento e exfiltração de PII.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Um desenvolvedor ou IA pode consultar o currículo apenas por 'resume_id' na camada de exportação
    sob o pretexto de simplificar o pipeline de geração de documentos, negligenciando a checagem 'user_id'.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    As rotas de exportação DOCX e PDF acionadas pelo User B contra 'resume_id' do User A
    devem falhar estritamente com código 404.
    """
    resume_id = setup_resumes["resume_id"]
    headers_b = setup_resumes["headers_b"]

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_B):
        res_docx = await async_client.get(
            f"/api/v1/resumes/{resume_id}/export/docx",
            headers=headers_b,
        )
        assert res_docx.status_code == 404

        res_pdf = await async_client.get(
            f"/api/v1/resumes/{resume_id}/export/pdf",
            headers=headers_b,
        )
        assert res_pdf.status_code == 404
