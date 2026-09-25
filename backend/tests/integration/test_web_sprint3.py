"""Testes de integração para os fluxos da Sprint 3: Live Split-View e Funil ATS Pessoal.

Valida a edição ao vivo de currículos com re-renderização A4 em tempo real,
auditoria algorítmica de fidelidade factual, exportação binária PDF/DOCX,
quadro Kanban com 6 estágios, alertas de follow-up e notas de processo.
"""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.api.v1.schemas.application import (
    ApplicationAnalyticsMetrics,
    ApplicationDetailResponse,
    ApplicationListItemResponse,
    ApplicationNoteResponse,
)
from app.api.web import _extract_updated_resume_content
from app.core.grounding_audit import AuditResult, HallucinationIssue, HallucinationSeverity
from app.domain.models import Application, GeneratedResume, User

MOCK_USER_ID = uuid.uuid4()
MOCK_RESUME_ID = uuid.uuid4()
MOCK_APP_ID = uuid.uuid4()

MOCK_WEB_USER = User(
    id=MOCK_USER_ID,
    firebase_uid="firebase_sprint3_tester_uid",
    email="sprint3_tester@thothcvs.ai",
    full_name="Renata Tech Lead",
    target_title="Staff Backend Engineer",
    phone="+55 11 98888-7777",
    location="São Paulo, SP",
    linkedin_url="https://linkedin.com/in/renatalead",
    github_url="https://github.com/renatalead",
)

MOCK_STRUCTURED_CONTENT = {
    "header": {
        "full_name": "Renata Tech Lead",
        "target_title": "Staff Backend Engineer",
        "email": "renata@example.com",
        "phone": "+55 11 98888-7777",
        "location": "São Paulo, SP",
        "linkedin_url": "https://linkedin.com/in/renatalead",
        "github_url": "https://github.com/renatalead",
    },
    "professional_summary": "Engenheira de software sênior com 10 anos de experiência.",
    "selected_experiences": [
        {
            "company_name": "Nubank",
            "position_title": "Senior Software Engineer",
            "start_date": "2021",
            "end_date": "2024",
            "tech_stack": ["Python", "FastAPI", "PostgreSQL"],
            "bullet_points": ["Redução de latência p99 em 30%."],
            "achievements": ["Redução de latência p99 em 30%."],
        }
    ],
    "skills_highlighted": ["Python", "PostgreSQL", "Docker", "FastAPI"],
    "skills": ["Python", "PostgreSQL", "Docker", "FastAPI"],
    "education": [
        {
            "degree": "Bacharelado",
            "field_of_study": "Ciência da Computação",
            "institution_name": "USP",
            "start_date": "2010",
            "end_date": "2014",
        }
    ],
    "certifications": [{"name": "GCP Cloud Architect", "issuing_organization": "Google"}],
    "languages": [{"language": "Português", "proficiency": "Nativo"}],
}

MOCK_RESUME = GeneratedResume(
    id=MOCK_RESUME_ID,
    application_id=MOCK_APP_ID,
    user_id=MOCK_USER_ID,
    language="pt-BR",
    version_number=1,
    structured_content=MOCK_STRUCTURED_CONTENT,
    match_percentage=88.5,
    created_at=datetime.now(UTC),
    updated_at=datetime.now(UTC),
)

MOCK_APPLICATION = Application(
    id=MOCK_APP_ID,
    user_id=MOCK_USER_ID,
    company_name="Google",
    job_title="Staff Backend Engineer",
    status="applied",
    work_model="remote",
    salary_range="R$ 30k - 35k",
    location="São Paulo / Remoto",
    job_url="https://google.com/jobs/123",
    job_description="Requisitos: Python avançado, arquitetura hexagonal, microsserviços.",
    last_activity_at=datetime.now(UTC),
    reminder_active=True,
)


# ==============================================================================
# GUARDRAILS ANTI-REGRESSÃO: AUTENTICAÇÃO FAIL-CLOSED (SPRINT 3)
# ==============================================================================


@pytest.mark.asyncio
async def test_guardrail_resume_preview_unauthenticated_redirects(
    async_client: AsyncClient,
) -> None:
    """Valida proteção fail-closed contra visualização não autorizada de currículo sob medida.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Vazamento de dados pessoais de candidatos e acesso não autorizado.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Requisições anônimas DEVEM ser interceptadas e redirecionadas para '/?auth_error=login_required' com status 302.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Qualquer tentativa de flexibilizar a rota para permitir pré-visualização sem sessão expõe PII em trânsito.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - GET /resumes/{uuid}/preview sem sessão válida DEVE resultar em HTTP 302 com Location para login.
    """
    res = await async_client.get(f"/resumes/{MOCK_RESUME_ID}/preview", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=login_required"


@pytest.mark.asyncio
async def test_guardrail_resume_preview_render_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed que rejeita re-renderização em tempo real de requisições anônimas.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function / CSRF.
    - Impacto Potencial: Processamento computacional arbitrário de dados não autenticados.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Chamadas POST anônimas via HTMX DEVEM retornar HTTP 401 e script de redirecionamento.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Tratar ausência de usuário como fallback vazio causaria vazamento de template com dados corrompidos.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /resumes/{uuid}/preview-render sem sessão DEVE responder com HTTP 401.
    """
    res = await async_client.post(f"/resumes/{MOCK_RESUME_ID}/preview-render", data={})
    assert res.status_code == 401
    assert "login_required" in res.text


@pytest.mark.asyncio
async def test_guardrail_resume_save_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida proteção fail-closed que bloqueia persistência de edições de currículo sem sessão ativa.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Corrupção maliciosa de currículos persistidos no banco de dados.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - POST /resumes/{uuid}/save sem cookie HTTP-only de sessão DEVE falhar imediatamente com HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Permitir salvar sem conferência de tenant permitiria sobrescrita de dados de terceiros.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /resumes/{uuid}/save sem sessão DEVE retornar HTTP 401.
    """
    res = await async_client.post(f"/resumes/{MOCK_RESUME_ID}/save", data={})
    assert res.status_code == 401
    assert "login_required" in res.text


@pytest.mark.asyncio
async def test_guardrail_resume_verify_grounding_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida proteção fail-closed da auditoria factual contra requisições sem autenticação.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Exploração indevida de CPU e scraping de regras de validação.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Auditoria de grounding DEVE exigir usuário logado e retornar HTTP 401 caso contrário.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Se a rota for aberta, agentes poderiam orquestrar testes de alucinação sem credenciais válidas.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /resumes/{uuid}/verify-grounding sem sessão DEVE retornar HTTP 401.
    """
    res = await async_client.post(f"/resumes/{MOCK_RESUME_ID}/verify-grounding", data={})
    assert res.status_code == 401
    assert "login_required" in res.text


@pytest.mark.asyncio
async def test_guardrail_resume_export_pdf_unauthenticated_redirects(
    async_client: AsyncClient,
) -> None:
    """Valida que downloads de PDF exigem sessão autenticada legítima.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Exfiltração de currículos gerados em formato PDF.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - GET /resumes/{uuid}/export/pdf sem cookie de sessão DEVE redirecionar com HTTP 302 para login.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Links públicos não assinados para PDF permitiriam enumeração de UUIDs (IDOR).

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - GET anônimo em /resumes/{uuid}/export/pdf DEVE retornar HTTP 302.
    """
    res = await async_client.get(f"/resumes/{MOCK_RESUME_ID}/export/pdf", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=login_required"


@pytest.mark.asyncio
async def test_guardrail_resume_export_docx_unauthenticated_redirects(
    async_client: AsyncClient,
) -> None:
    """Valida que downloads de DOCX exigem sessão autenticada legítima.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Exfiltração de currículos gerados em formato DOCX.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - GET /resumes/{uuid}/export/docx sem cookie de sessão DEVE redirecionar com HTTP 302 para login.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Permitir downloads diretos sem token compromete o isolamento multi-tenant.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - GET anônimo em /resumes/{uuid}/export/docx DEVE retornar HTTP 302.
    """
    res = await async_client.get(f"/resumes/{MOCK_RESUME_ID}/export/docx", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=login_required"


@pytest.mark.asyncio
async def test_guardrail_applications_unauthenticated_redirects(
    async_client: AsyncClient,
) -> None:
    """Valida proteção fail-closed da página principal do Funil ATS Pessoal.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Acesso a dados de vagas, empresas abordadas e anotações confidenciais.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Acessos anônimos a GET /applications DEVEM responder com HTTP 302 redirecionando para login.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Renderizar a página sem usuário causaria falha em cascata ou exposição de funil vazio.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - GET /applications sem sessão DEVE redirecionar com HTTP 302 para '/?auth_error=login_required'.
    """
    res = await async_client.get("/applications", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=login_required"


@pytest.mark.asyncio
async def test_guardrail_applications_create_unauthenticated_redirects(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed que impede criação de vagas por visitantes sem sessão.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Poluição de dados da base por agentes anônimos.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - POST /applications/create sem sessão DEVE responder com HTTP 302 para login.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Criar oportunidade sem vincular a user_id violaria integridade relacional.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /applications/create sem sessão DEVE retornar HTTP 302.
    """
    res = await async_client.post(
        "/applications/create",
        data={"company_name": "TestCorp", "job_title": "Engineer"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=login_required"


@pytest.mark.asyncio
async def test_guardrail_applications_status_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida proteção fail-closed para atualização de status de candidatura no Kanban.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Alteração indevida de estágios seletivos por agentes não autorizados.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - POST /applications/{uuid}/status sem sessão DEVE retornar HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Aceitar transição sem conferir dono da vaga permitiria ataques de manipulação de pipeline.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /applications/{uuid}/status sem sessão DEVE retornar HTTP 401.
    """
    res = await async_client.post(
        f"/applications/{MOCK_APP_ID}/status",
        data={"new_status": "screen"},
    )
    assert res.status_code == 401
    assert "login_required" in res.text


@pytest.mark.asyncio
async def test_guardrail_applications_detail_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida proteção fail-closed do modal de detalhes da oportunidade.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Visualização indevida de histórico de entrevistas e contatos de RH.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - GET /applications/{uuid}/detail sem sessão DEVE retornar HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Deixar rota aberta abriria brecha de privacidade LGPD dos contatos de recrutadores.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - GET /applications/{uuid}/detail sem sessão DEVE retornar HTTP 401.
    """
    res = await async_client.get(f"/applications/{MOCK_APP_ID}/detail")
    assert res.status_code == 401
    assert "login_required" in res.text


@pytest.mark.asyncio
async def test_guardrail_applications_notes_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida proteção fail-closed para inclusão de anotações confidenciais.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Injeção de notas arbitrárias em processos seletivos.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - POST /applications/{uuid}/notes sem sessão DEVE retornar HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Aceitar anotações sem checagem de tenant permitiria vandalismo de registros.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /applications/{uuid}/notes sem sessão DEVE retornar HTTP 401.
    """
    res = await async_client.post(
        f"/applications/{MOCK_APP_ID}/notes",
        data={"content": "Nota de teste", "note_type": "technical"},
    )
    assert res.status_code == 401
    assert "login_required" in res.text


@pytest.mark.asyncio
async def test_guardrail_applications_modal_create_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida proteção fail-closed para abertura do modal de cadastro de oportunidade.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Acesso a fragmentos de UI destinados a usuários cadastrados.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - GET /applications/modal/create sem sessão DEVE responder com HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Carregar o formulário anônimo geraria falhas de submissão subsequentes.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - GET /applications/modal/create sem sessão DEVE retornar HTTP 401.
    """
    res = await async_client.get("/applications/modal/create")
    assert res.status_code == 401
    assert "login_required" in res.text


# ==============================================================================
# FLUXOS AUTENTICADOS: LIVE SPLIT-VIEW & EDITOR DE CURRÍCULOS
# ==============================================================================


@pytest.mark.asyncio
async def test_resume_preview_page_authenticated_renders(async_client: AsyncClient) -> None:
    """Valida renderização completa do Live Split-View para o dono do currículo."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_result_resume = MagicMock()
    mock_db_result_resume.scalar_one_or_none.return_value = MOCK_RESUME

    mock_db_result_app = MagicMock()
    mock_db_result_app.scalar_one_or_none.return_value = MOCK_APPLICATION

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            side_effect=[mock_db_result_resume, mock_db_result_app],
        ),
    ):
        res = await async_client.get(f"/resumes/{MOCK_RESUME_ID}/preview")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        content = res.text
        assert "Editor e Visualização ao Vivo" in content
        assert "Currículo Sob Medida" in content
        assert "v1" in content
        assert "88.5% Match" in content
        assert "Editor de Campos do Currículo" in content
        assert "Visualização ATS Real" in content
        assert "Auditar Fidelidade Factual" in content
        assert "Salvar" in content


@pytest.mark.asyncio
async def test_resume_preview_page_not_found_returns_404(async_client: AsyncClient) -> None:
    """Valida que acessar currículo inexistente ou de outro usuário resulta em 404."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = None

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_result,
        ),
    ):
        res = await async_client.get(f"/resumes/{uuid.uuid4()}/preview")
        assert res.status_code == 404
        assert "Currículo não encontrado" in res.json().get("detail", "")


@pytest.mark.asyncio
async def test_resume_preview_render_live_updates_a4_paper(async_client: AsyncClient) -> None:
    """Valida re-renderização instantânea via HTMX da folha A4 com dados editados."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = MOCK_RESUME

    form_payload = {
        "target_title": "Principal Distributed Systems Engineer",
        "professional_summary": "Resumo modificado em tempo real pelo usuário.",
        "skills_list": "Rust, Golang, Kubernetes, Kafka",
        "exp_0_title": "Tech Lead de Infraestrutura",
        "exp_0_company": "Nubank Global",
        "exp_0_period": "2020 — 2024",
        "exp_0_bullets": "Liderança de 12 engenheiros.\nMigração zero-downtime.",
    }

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_result,
        ),
    ):
        res = await async_client.post(
            f"/resumes/{MOCK_RESUME_ID}/preview-render",
            data=form_payload,
        )
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        content = res.text
        assert "Principal Distributed Systems Engineer" in content
        assert "Resumo modificado em tempo real pelo usuário." in content
        assert "Tech Lead de Infraestrutura" in content
        assert "Nubank Global" in content
        assert "Rust" in content
        assert "Liderança de 12 engenheiros." in content


@pytest.mark.asyncio
async def test_resume_preview_render_not_found_returns_404(async_client: AsyncClient) -> None:
    """Valida 404 ao tentar renderizar preview de currículo inexistente."""
    async_client.cookies.set("session_token", "valid_session_token")
    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = None

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_result,
        ),
    ):
        res = await async_client.post(f"/resumes/{uuid.uuid4()}/preview-render", data={})
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_resume_save_content_persists_changes(async_client: AsyncClient) -> None:
    """Valida persistência atômica das alterações manuais e feedback visual toast."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = MOCK_RESUME

    form_payload = {
        "target_title": "Lead Software Architect",
        "professional_summary": "Sumário salvo permanentemente.",
        "skills_list": "Python, FastAPI",
    }

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_result,
        ),
        patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock) as mock_commit,
    ):
        res = await async_client.post(
            f"/resumes/{MOCK_RESUME_ID}/save",
            data=form_payload,
        )
        assert res.status_code == 200
        assert "Alterações do currículo salvas com sucesso!" in res.text
        mock_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_save_content_not_found_returns_404(async_client: AsyncClient) -> None:
    """Valida retorno 404 ao tentar salvar currículo não existente."""
    async_client.cookies.set("session_token", "valid_session_token")
    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = None

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_result,
        ),
    ):
        res = await async_client.post(f"/resumes/{uuid.uuid4()}/save", data={})
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_resume_verify_grounding_audit_renders_card(async_client: AsyncClient) -> None:
    """Valida execução da auditoria algorítmica de grounding com renderização de card."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = MOCK_RESUME

    mock_dossier = {
        "experiences": [MagicMock(company_name="Nubank")],
        "skills": [MagicMock(name="Python"), MagicMock(name="FastAPI")],
        "educations": [MagicMock(degree="Bacharelado")],
    }

    mock_audit = AuditResult(
        is_valid=True,
        trust_score=100.0,
        severity=HallucinationSeverity.LOW,
        hallucinations=[],
        verified_counts_by_tier={"syntactic": 3},
    )

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_result,
        ),
        patch(
            "app.services.profile_service.ProfileService.get_full_dossier",
            new_callable=AsyncMock,
            return_value=mock_dossier,
        ),
        patch(
            "app.core.grounding_audit.GroundingAuditEngine.audit",
            return_value=mock_audit,
        ),
    ):
        res = await async_client.post(
            f"/resumes/{MOCK_RESUME_ID}/verify-grounding",
            data={"target_title": "Staff Backend Engineer"},
        )
        assert res.status_code == 200
        assert "Fidelidade Factual Verificada: 100% de Veracidade" in res.text
        assert "100.0%" in res.text


@pytest.mark.asyncio
async def test_resume_verify_grounding_with_hallucinations(async_client: AsyncClient) -> None:
    """Valida exibição de discrepâncias identificadas na auditoria de fidelidade."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = MOCK_RESUME

    mock_audit = AuditResult(
        is_valid=False,
        trust_score=75.0,
        severity=HallucinationSeverity.CRITICAL,
        hallucinations=[
            HallucinationIssue(
                field="selected_experiences.company_name",
                hallucinated_value="FakeCorp",
                description="Empresa não cadastrada no perfil: 'FakeCorp'",
                severity=HallucinationSeverity.CRITICAL,
            )
        ],
        verified_counts_by_tier={"syntactic": 3},
    )

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_result,
        ),
        patch(
            "app.services.profile_service.ProfileService.get_full_dossier",
            new_callable=AsyncMock,
            return_value={"experiences": [], "skills": [], "educations": []},
        ),
        patch(
            "app.core.grounding_audit.GroundingAuditEngine.audit",
            return_value=mock_audit,
        ),
    ):
        res = await async_client.post(
            f"/resumes/{MOCK_RESUME_ID}/verify-grounding",
            data={},
        )
        assert res.status_code == 200
        assert "Auditoria Anti-Alucinação: 1 ponto(s) de atenção" in res.text
        assert "FakeCorp" in res.text


@pytest.mark.asyncio
async def test_resume_verify_grounding_not_found_returns_404(async_client: AsyncClient) -> None:
    """Valida 404 para auditoria em currículo não encontrado."""
    async_client.cookies.set("session_token", "valid_session_token")
    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = None

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_result,
        ),
    ):
        res = await async_client.post(f"/resumes/{uuid.uuid4()}/verify-grounding", data={})
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_resume_export_pdf_authenticated_success(async_client: AsyncClient) -> None:
    """Valida exportação binária de PDF autenticada com cabeçalhos apropriados."""
    async_client.cookies.set("session_token", "valid_session_token")
    fake_pdf = b"%PDF-1.4 mock binary content"

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.document_service.DocumentService.export_pdf",
            new_callable=AsyncMock,
            return_value=(fake_pdf, "curriculo_teste.pdf"),
        ),
    ):
        res = await async_client.get(f"/resumes/{MOCK_RESUME_ID}/export/pdf")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert 'attachment; filename="curriculo_teste.pdf"' in res.headers["content-disposition"]
        assert res.content == fake_pdf


@pytest.mark.asyncio
async def test_resume_export_docx_authenticated_success(async_client: AsyncClient) -> None:
    """Valida exportação binária de DOCX autenticada com cabeçalhos apropriados."""
    async_client.cookies.set("session_token", "valid_session_token")
    fake_docx = b"PK\x03\x04 mock word document"

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.document_service.DocumentService.export_docx",
            new_callable=AsyncMock,
            return_value=(fake_docx, "curriculo_teste.docx"),
        ),
    ):
        res = await async_client.get(f"/resumes/{MOCK_RESUME_ID}/export/docx")
        assert res.status_code == 200
        assert (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            in res.headers["content-type"]
        )
        assert 'attachment; filename="curriculo_teste.docx"' in res.headers["content-disposition"]
        assert res.content == fake_docx


# ==============================================================================
# FLUXOS AUTENTICADOS: FUNIL ATS PESSOAL & KANBAN
# ==============================================================================


@pytest.mark.asyncio
async def test_applications_funnel_page_renders_with_metrics(async_client: AsyncClient) -> None:
    """Valida visualização do painel de candidaturas com métricas consolidadas e colunas."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_app_item = ApplicationListItemResponse(
        id=MOCK_APP_ID,
        company_name="Google",
        job_title="Staff Backend Engineer",
        status="applied",
        work_model="remote",
        applied_at=date.today(),
        last_activity_at=datetime.now(UTC),
        needs_follow_up=True,
        salary_range="R$ 30k",
    )

    mock_analytics = ApplicationAnalyticsMetrics(
        total_applications=1,
        status_distribution={"applied": 1},
        stale_applications_count=1,
        interview_conversion_rate=0.0,
        offer_conversion_rate=0.0,
        average_match_score=88.5,
    )

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.application_service.ApplicationService.list_applications",
            new_callable=AsyncMock,
            return_value=[mock_app_item],
        ),
        patch(
            "app.services.application_service.ApplicationService.get_analytics_metrics",
            new_callable=AsyncMock,
            return_value=mock_analytics,
        ),
    ):
        res = await async_client.get("/applications")
        assert res.status_code == 200
        content = res.text
        assert "Funil ATS Pessoal" in content
        assert "Total de Vagas" in content
        assert "Exigem Follow-up" in content
        assert "Google" in content
        assert "Staff Backend Engineer" in content
        assert "Sem contato há mais de 7 dias" in content


@pytest.mark.asyncio
async def test_applications_create_modal_renders_accessible_dialog(
    async_client: AsyncClient,
) -> None:
    """Valida carregamento do fragmento HTML do modal de nova oportunidade."""
    async_client.cookies.set("session_token", "valid_session_token")

    with patch(
        "app.services.auth_service.AuthService.get_authenticated_user",
        new_callable=AsyncMock,
        return_value=MOCK_WEB_USER,
    ):
        res = await async_client.get("/applications/modal/create")
        assert res.status_code == 200
        content = res.text
        assert 'role="dialog"' in content
        assert 'aria-modal="true"' in content
        assert "Nova Candidatura ATS" in content
        assert "Empresa" in content
        assert "Cargo / Título" in content


@pytest.mark.asyncio
async def test_applications_create_new_opportunity_htmx_redirect(
    async_client: AsyncClient,
) -> None:
    """Valida cadastro de candidatura com retorno de cabeçalho HX-Redirect."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_created = ApplicationListItemResponse(
        id=uuid.uuid4(),
        company_name="Amazon AWS",
        job_title="Principal Architect",
        status="applied",
        work_model="remote",
        applied_at=date.today(),
        last_activity_at=datetime.now(UTC),
        needs_follow_up=False,
    )

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.application_service.ApplicationService.create_application",
            new_callable=AsyncMock,
            return_value=mock_created,
        ),
    ):
        res = await async_client.post(
            "/applications/create",
            headers={"HX-Request": "true"},
            data={
                "company_name": "Amazon AWS",
                "job_title": "Principal Architect",
                "status": "applied",
                "work_model": "remote",
                "salary_range": "R$ 35k",
            },
        )
        assert res.status_code == 200
        assert res.headers.get("hx-redirect") == "/applications"


@pytest.mark.asyncio
async def test_applications_create_new_opportunity_standard_redirect(
    async_client: AsyncClient,
) -> None:
    """Valida cadastro de candidatura via formulário padrão sem HTMX (HTTP 302)."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_created = ApplicationListItemResponse(
        id=uuid.uuid4(),
        company_name="Microsoft",
        job_title="Lead Dev",
        status="applied",
        work_model="hybrid",
        applied_at=date.today(),
        last_activity_at=datetime.now(UTC),
        needs_follow_up=False,
    )

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.application_service.ApplicationService.create_application",
            new_callable=AsyncMock,
            return_value=mock_created,
        ),
    ):
        res = await async_client.post(
            "/applications/create",
            data={
                "company_name": "Microsoft",
                "job_title": "Lead Dev",
                "status": "applied",
            },
            follow_redirects=False,
        )
        assert res.status_code == 302
        assert res.headers["location"] == "/applications"


@pytest.mark.asyncio
async def test_applications_status_transition_updates_kanban(async_client: AsyncClient) -> None:
    """Valida avanço de etapa no Kanban e retorno do tabuleiro HTML atualizado."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_updated_app = ApplicationListItemResponse(
        id=MOCK_APP_ID,
        company_name="Google",
        job_title="Staff Backend Engineer",
        status="tech_interview",
        work_model="remote",
        applied_at=date.today(),
        last_activity_at=datetime.now(UTC),
        needs_follow_up=False,
    )

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.application_service.ApplicationService.update_application",
            new_callable=AsyncMock,
            return_value=mock_updated_app,
        ),
        patch(
            "app.services.application_service.ApplicationService.list_applications",
            new_callable=AsyncMock,
            return_value=[mock_updated_app],
        ),
    ):
        res = await async_client.post(
            f"/applications/{MOCK_APP_ID}/status",
            data={"new_status": "tech_interview"},
        )
        assert res.status_code == 200
        content = res.text
        assert 'id="kanban-board"' in content
        assert "Google" in content
        assert "Entrevista Técnica" in content


@pytest.mark.asyncio
async def test_applications_detail_modal_with_resumes_and_notes(async_client: AsyncClient) -> None:
    """Valida renderização do dossiê detalhado com lista de currículos e feed de notas."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_detail = ApplicationDetailResponse(
        id=MOCK_APP_ID,
        company_name="Google",
        job_title="Staff Backend Engineer",
        job_description="Descrição da vaga de alta relevância.",
        job_url="https://google.com/jobs/123",
        status="tech_interview",
        work_model="remote",
        salary_range="R$ 32k",
        location="São Paulo, SP",
        applied_at=date.today(),
        last_activity_at=datetime.now(UTC),
        reminder_active=True,
        needs_follow_up=False,
        stages=[],
        contacts=[],
        notes=[
            ApplicationNoteResponse(
                id=uuid.uuid4(),
                application_id=MOCK_APP_ID,
                content="Entrevista com o EM agendada para sexta-feira.",
                note_type="technical",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        ],
    )

    mock_db_resumes = MagicMock()
    mock_db_resumes.scalars.return_value.all.return_value = [MOCK_RESUME]

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.application_service.ApplicationService.get_application_detail",
            new_callable=AsyncMock,
            return_value=mock_detail,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_resumes,
        ),
    ):
        res = await async_client.get(f"/applications/{MOCK_APP_ID}/detail")
        assert res.status_code == 200
        content = res.text
        assert 'role="dialog"' in content
        assert "Google" in content
        assert "Entrevista com o EM agendada" in content
        assert "v1" in content
        assert "Abrir no Split-View" in content


@pytest.mark.asyncio
async def test_applications_add_note_appends_to_feed(async_client: AsyncClient) -> None:
    """Valida registro de anotação de processo seletivo via HTMX."""
    async_client.cookies.set("session_token", "valid_session_token")

    new_note = ApplicationNoteResponse(
        id=uuid.uuid4(),
        application_id=MOCK_APP_ID,
        content="Passou na etapa de triagem técnica com nota máxima.",
        note_type="screening",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    mock_detail = ApplicationDetailResponse(
        id=MOCK_APP_ID,
        company_name="Google",
        job_title="Staff Backend Engineer",
        job_description="Descrição da vaga.",
        status="applied",
        work_model="remote",
        applied_at=date.today(),
        last_activity_at=datetime.now(UTC),
        reminder_active=True,
        needs_follow_up=False,
        stages=[],
        contacts=[],
        notes=[new_note],
    )

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.application_service.ApplicationService.add_note",
            new_callable=AsyncMock,
            return_value=new_note,
        ),
        patch(
            "app.services.application_service.ApplicationService.get_application_detail",
            new_callable=AsyncMock,
            return_value=mock_detail,
        ),
    ):
        res = await async_client.post(
            f"/applications/{MOCK_APP_ID}/notes",
            data={"content": new_note.content, "note_type": new_note.note_type},
        )
        assert res.status_code == 200
        content = res.text
        assert 'id="app-notes-section"' in content
        assert "Passou na etapa de triagem técnica" in content
        assert "screening" in content


# ==============================================================================
# TESTE UNITÁRIO: HELPER _extract_updated_resume_content
# ==============================================================================


def test_extract_updated_resume_content_variations() -> None:
    """Valida parsing e atualização correta de metadados, experiências e competências."""
    base = {
        "header": {"target_title": "Old Title", "email": "dev@test.com"},
        "professional_summary": "Old Summary",
        "selected_experiences": [
            {
                "company_name": "OldCo",
                "position_title": "OldPos",
                "start_date": "2019",
                "end_date": "2020",
                "tech_stack": ["Python"],
                "bullet_points": ["Old achievement"],
            }
        ],
        "skills_highlighted": ["Python"],
    }

    # Caso 1: Período com hífen simples
    form_hyphen = {
        "target_title": "New Title",
        "professional_summary": "New Summary",
        "skills_list": "FastAPI, PostgreSQL, Redis",
        "exp_0_title": "Senior Engineer",
        "exp_0_company": "NewCo",
        "exp_0_period": "2021 - 2023",
        "exp_0_bullets": "Impact 1\nImpact 2",
    }
    updated = _extract_updated_resume_content(base, form_hyphen)
    assert updated["header"]["target_title"] == "New Title"
    assert updated["header"]["email"] == "dev@test.com"  # preservado
    assert updated["professional_summary"] == "New Summary"
    assert updated["skills_highlighted"] == ["FastAPI", "PostgreSQL", "Redis"]
    assert updated["selected_experiences"][0]["start_date"] == "2021"
    assert updated["selected_experiences"][0]["end_date"] == "2023"
    assert len(updated["selected_experiences"][0]["bullet_points"]) == 2

    # Caso 2: Período com data única sem traço e chave com índice inválido
    form_single = {
        "exp_0_title": "Lead",
        "exp_0_company": "SingleCo",
        "exp_0_period": "2024",
        "exp_0_bullets": "Single line",
        "exp_invalid_title": "Ignored",
    }
    updated2 = _extract_updated_resume_content(base, form_single)
    assert updated2["selected_experiences"][0]["start_date"] == "2024"
    assert updated2["selected_experiences"][0]["end_date"] == ""
    assert updated2["selected_experiences"][0]["end_date"] == ""
