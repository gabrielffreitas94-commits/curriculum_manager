"""Testes de integração para as rotas web do Dossiê Profissional (app/api/web.py).

Valida a renderização HTML do Dossiê, upload HTMX de currículo, modal de revisão
e confirmação de importação com controle de sessão e guardrails anti-regressão.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.domain.models import User
from app.ports.resume_parser_port import (
    ParsedEducationDTO,
    ParsedExperienceDTO,
    ParsedPersonalDataDTO,
    ParsedProfileDTO,
    ParsedSkillDTO,
    ResumeParserError,
)

MOCK_USER_ID = uuid.uuid4()
MOCK_WEB_USER = User(
    id=MOCK_USER_ID,
    firebase_uid="firebase_web_tester_uid",
    email="web_tester@thothcvs.ai",
    full_name="Web Tester",
    target_title="Staff Software Engineer",
    phone="+55 11 91234-5678",
    location="São Paulo, SP",
    linkedin_url="https://linkedin.com/in/webtester",
    github_url="https://github.com/webtester",
)


@pytest.mark.asyncio
async def test_guardrail_profile_page_unauthenticated_redirects(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed que redireciona acessos não autenticados ao Dossiê.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Acesso indevido a dados de perfil e documentos sem sessão.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Requisições sem cookie válido DEVEM retornar HTTP 302 para '/?auth_error=login_required'.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Permitir renderização parcial de perfil sem usuário causaria vazamento ou exceções 500.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Acesso anônimo a GET /profile DEVE responder exatamente HTTP 302.
    """
    res = await async_client.get("/profile", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=login_required"


@pytest.mark.asyncio
async def test_profile_page_authenticated_renders_dossier(async_client: AsyncClient) -> None:
    """Valida renderização completa da página do Dossiê para usuário logado."""
    async_client.cookies.set("session_token", "valid_session_token")
    with patch(
        "app.services.auth_service.AuthService.get_authenticated_user",
        new_callable=AsyncMock,
        return_value=MOCK_WEB_USER,
    ):
        res = await async_client.get("/profile")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        content = res.text
        assert "Meu Dossiê Profissional" in content
        assert "Web Tester" in content
        assert "Staff Software Engineer" in content
        assert "Carregar Currículo" in content
        assert "Experiências Profissionais" in content
        assert "Competências" in content
        assert "Formação Acadêmica" in content


@pytest.mark.asyncio
async def test_import_cv_upload_unauthenticated_returns_401_script(
    async_client: AsyncClient,
) -> None:
    """Valida que upload sem sessão retorna script de redirecionamento 401."""
    files = {"file": ("cv.pdf", b"%PDF-1.4 mock", "application/pdf")}
    res = await async_client.post("/profile/import-cv", files=files)
    assert res.status_code == 401
    assert "window.location.href" in res.text


@pytest.mark.asyncio
async def test_import_cv_upload_invalid_file_returns_error_modal(async_client: AsyncClient) -> None:
    """Valida que arquivo inválido (ex: extensão .exe) retorna modal de erro com HTTP 400."""
    async_client.cookies.set("session_token", "valid_session_token")
    with patch(
        "app.services.auth_service.AuthService.get_authenticated_user",
        new_callable=AsyncMock,
        return_value=MOCK_WEB_USER,
    ):
        files = {"file": ("malware.exe", b"not_allowed", "application/octet-stream")}
        res = await async_client.post("/profile/import-cv", files=files)
        assert res.status_code == 400
        assert "Falha no Envio do Arquivo" in res.text
        assert "não suportada" in res.text


@pytest.mark.asyncio
async def test_import_cv_upload_parser_error_returns_modal(async_client: AsyncClient) -> None:
    """Valida tratamento de falha na extração retornando modal explicativo com HTTP 422."""
    async_client.cookies.set("session_token", "valid_session_token")
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch("app.api.web.get_resume_parser_adapter") as mock_get_parser,
    ):
        mock_parser = AsyncMock()
        mock_parser.parse_resume.side_effect = ResumeParserError("Cota do Gemini indisponível")
        mock_get_parser.return_value = mock_parser

        files = {"file": ("curriculo.pdf", b"%PDF-1.4 content", "application/pdf")}
        res = await async_client.post("/profile/import-cv", files=files)
        assert res.status_code == 422
        assert "Não foi possível analisar o currículo" in res.text
        assert "Cota do Gemini indisponível" in res.text


@pytest.mark.asyncio
async def test_import_cv_upload_success_returns_review_modal(async_client: AsyncClient) -> None:
    """Valida fluxo feliz de upload e renderização do modal de conferência dos dados extraídos."""
    mock_dto = ParsedProfileDTO(
        personal_data=ParsedPersonalDataDTO(
            full_name="Alice Developer",
            headline="Backend Specialist",
            phone="+55 11 98765-4321",
            location="São Paulo, SP",
            linkedin_url="https://linkedin.com/in/alicedev",
        ),
        experiences=[
            ParsedExperienceDTO(
                company_name="Mega Corp",
                position_title="Senior Python Engineer",
                start_date="2021-01-01",
                is_current=True,
                description="Desenvolvimento de APIs com FastAPI.",
                tech_stack=["Python", "FastAPI"],
            )
        ],
        educations=[
            ParsedEducationDTO(
                institution_name="USP",
                degree="Bacharelado",
                field_of_study="Ciência da Computação",
                start_date="2016-01-01",
                end_date="2020-12-31",
                is_current=False,
            )
        ],
        skills=[ParsedSkillDTO(name="FastAPI", category="backend", years_of_experience=4)],
    )

    async_client.cookies.set("session_token", "valid_session_token")
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch("app.api.web.get_resume_parser_adapter") as mock_get_parser,
    ):
        mock_parser = AsyncMock()
        mock_parser.parse_resume.return_value = mock_dto
        mock_get_parser.return_value = mock_parser

        files = {"file": ("curriculo_alice.pdf", b"%PDF-1.4 authentic content", "application/pdf")}
        res = await async_client.post("/profile/import-cv", files=files)
        assert res.status_code == 200
        assert "Currículo Analisado com Sucesso" in res.text
        assert "Alice Developer" in res.text
        assert "Mega Corp" in res.text
        assert "Senior Python Engineer" in res.text
        assert "FastAPI" in res.text
        assert "Confirmar e Integrar ao Dossiê" in res.text


@pytest.mark.asyncio
async def test_confirm_profile_import_flow(async_client: AsyncClient) -> None:
    """Valida confirmação e persistência dos dados revisados via HTMX."""
    mock_dto = ParsedProfileDTO(
        personal_data=ParsedPersonalDataDTO(full_name="Confirmed User"),
        experiences=[
            ParsedExperienceDTO(
                company_name="Confirmed Company",
                position_title="Software Architect",
                start_date="2022-01-01",
                is_current=True,
            )
        ],
    )
    serialized = mock_dto.model_dump_json()

    # 1. Sem sessão -> Redireciona
    res_unauth = await async_client.post(
        "/profile/confirm-import",
        data={"payload": serialized},
        follow_redirects=False,
    )
    assert res_unauth.status_code == 302
    assert res_unauth.headers["location"] == "/?auth_error=login_required"

    # 2. Com sessão -> Sucesso com HX-Redirect
    async_client.cookies.set("session_token", "valid_session_token")
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.profile_service.ProfileService.import_parsed_profile",
            new_callable=AsyncMock,
            return_value={"experiences": 1},
        ) as mock_import,
    ):
        res = await async_client.post("/profile/confirm-import", data={"payload": serialized})
        assert res.status_code == 200
        assert res.headers["HX-Redirect"] == "/profile"
        mock_import.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_page_direct_rendering() -> None:
    """Valida execução e renderização direta da rota profile_page com o Dossiê."""
    from unittest.mock import MagicMock

    from fastapi import Request

    from app.api.web import profile_page

    req = MagicMock(spec=Request)
    req.scope = {"type": "http", "session": {}}
    profile_service_mock = AsyncMock()
    profile_service_mock.get_full_dossier.return_value = {
        "experiences": [],
        "educations": [],
        "skills": [],
        "languages": [],
        "certifications": [],
        "projects": [],
    }

    resp = await profile_page(
        request=req,
        current_user=MOCK_WEB_USER,
        profile_service=profile_service_mock,
    )
    assert resp.status_code == 200
    profile_service_mock.get_full_dossier.assert_awaited_once_with(MOCK_WEB_USER.id)
