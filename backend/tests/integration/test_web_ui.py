"""Testes de integração para a interface Web servida com HTMX e Jinja2."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request, Response
from httpx import AsyncClient

from app.api.web import (
    _set_session_cookie,
    get_authenticated_web_user,
    google_callback,
)
from app.core.config import settings
from app.domain.models import User
from app.ports.oauth_port import OAuthError, OAuthUserInfo
from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_welcome_page_renders_successfully(async_client: AsyncClient):
    """Valida renderização da página inicial de boas-vindas com HTMX e Tailwind compilado."""
    response = await async_client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    content = response.text

    assert "Bem-vindo" in content
    assert "/static/js/htmx.min.js" in content
    assert "/static/css/styles.css" in content
    assert "toggleTheme" in content
    assert "lang-dropdown-btn" in content
    assert "toggleLangDropdown" in content
    assert "current-lang-label" in content
    assert "login-btn" in content
    assert "/auth/modal" in content


@pytest.mark.asyncio
async def test_login_modal_renders_successfully(async_client: AsyncClient):
    """Valida renderização do fragmento HTML do modal de login com Google e LinkedIn."""
    response = await async_client.get("/auth/modal")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    content = response.text

    assert "Acessar Plataforma" in content
    assert "btn-login-google" in content
    assert "Continuar com o Google" in content
    assert "btn-login-linkedin" in content
    assert "Continuar com o LinkedIn" in content
    assert "Em breve" in content
    assert "closeModal" in content
    assert "Termos de Serviço" in content


@pytest.mark.asyncio
async def test_static_htmx_file_is_served(async_client: AsyncClient):
    """Valida disponibilidade do asset estático local htmx.min.js montado em /static."""
    response = await async_client.get("/static/js/htmx.min.js")

    assert response.status_code == 200
    assert "htmx" in response.text


@pytest.mark.asyncio
async def test_static_css_file_is_served(async_client: AsyncClient):
    """Valida disponibilidade do CSS compilado styles.css montado em /static."""
    response = await async_client.get("/static/css/styles.css")

    assert response.status_code == 200
    assert len(response.text) > 0


@pytest.mark.asyncio
async def test_logout_flow(async_client: AsyncClient):
    """Valida encerramento da sessão com remoção do cookie e refresh da tela."""
    res_logout = await async_client.post("/auth/logout")
    assert res_logout.status_code == 200
    assert res_logout.headers.get("HX-Refresh") == "true"


@pytest.mark.asyncio
async def test_welcome_page_with_invalid_or_empty_cookies(async_client: AsyncClient):
    """Valida que cookies inválidos ou vazios resultam em usuário anônimo sem exceções."""
    # Cookie vazio
    r_empty = await async_client.get("/", cookies={"session_token": "   "})
    assert r_empty.status_code == 200
    assert "login-btn" in r_empty.text

    # Cookie com token corrompido que falha na verificação
    r_invalid = await async_client.get("/", cookies={"session_token": "invalid_jwt_token_payload"})
    assert r_invalid.status_code == 200
    assert "login-btn" in r_invalid.text


@pytest.mark.asyncio
async def test_get_authenticated_web_user_direct():
    """Valida resolução direta de usuário autenticado na Web UI via AuthService."""
    # 1. Sem cookie / vazio
    req_no_cookie = MagicMock(spec=Request)
    req_no_cookie.cookies = {}
    auth_service_mock = MagicMock(spec=AuthService)
    auth_service_mock.get_authenticated_user = AsyncMock(return_value=None)
    user_none = await get_authenticated_web_user(req_no_cookie, auth_service_mock)
    assert user_none is None
    auth_service_mock.get_authenticated_user.assert_awaited_once_with(None)

    # 2. Com token válido e usuário encontrado
    req_with_cookie = MagicMock(spec=Request)
    req_with_cookie.cookies = {"session_token": "mock_direct_test_user"}
    user_mock = User(
        id=uuid.uuid4(), firebase_uid="mock_uid_mock_direct_test_user", email="direct@test.com"
    )
    auth_service_mock.get_authenticated_user = AsyncMock(return_value=user_mock)

    user_found = await get_authenticated_web_user(req_with_cookie, auth_service_mock)
    assert user_found == user_mock
    assert user_found.email == "direct@test.com"
    auth_service_mock.get_authenticated_user.assert_awaited_with("mock_direct_test_user")


@pytest.mark.asyncio
async def test_login_google_redirect(async_client: AsyncClient):
    """Valida redirecionamento HTTP 302 para a tela oficial do Google OAuth."""
    res = await async_client.get("/auth/login/google", follow_redirects=False)
    assert res.status_code == 302
    assert "https://accounts.google.com/o/oauth2/v2/auth" in res.headers["location"]
    assert "client_id=" in res.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_error_or_canceled(async_client: AsyncClient):
    """Valida redirecionamento quando o usuário cancela ou ocorre erro no consentimento."""
    # Com parâmetro error
    res_err = await async_client.get(
        "/auth/callback/google?error=access_denied", follow_redirects=False
    )
    assert res_err.status_code == 302
    assert res_err.headers["location"] == "/?auth_error=google_denied"

    # Sem código
    res_no_code = await async_client.get("/auth/callback/google", follow_redirects=False)
    assert res_no_code.status_code == 302
    assert res_no_code.headers["location"] == "/?auth_error=google_denied"


@pytest.mark.asyncio
async def test_google_callback_oauth_failure_and_invalid_token(async_client: AsyncClient):
    """Valida tratamento de falhas na troca de código e tokens inválidos."""
    # 1. Falha com OAuthError na troca de código
    with patch("app.api.web.google_oauth_adapter.exchange_code", new_callable=AsyncMock) as mock_ex:
        mock_ex.side_effect = OAuthError("Token exchange failed")
        res = await async_client.get("/auth/callback/google?code=bad_code", follow_redirects=False)
        assert res.status_code == 302
        assert res.headers["location"] == "/?auth_error=oauth_failed"

    # 2. Resposta sem access_token
    with patch("app.api.web.google_oauth_adapter.exchange_code", new_callable=AsyncMock) as mock_ex:
        mock_ex.return_value = {"error": "no_token"}
        res = await async_client.get(
            "/auth/callback/google?code=code_without_token", follow_redirects=False
        )
        assert res.status_code == 302
        assert res.headers["location"] == "/?auth_error=oauth_failed"


@pytest.mark.asyncio
async def test_google_callback_success_flow_new_and_existing_user(async_client: AsyncClient):
    """Valida fluxo completo com sucesso: novo usuário, emissão de cookie JWT e login existente."""
    user_info = OAuthUserInfo(
        sub="google_sub_123456",
        email="real.user@gmail.com",
        full_name="Real Google User",
        picture_url="https://lh3.googleusercontent.com/avatar.jpg",
    )

    # 1. Novo usuário logando via Google OAuth
    with (
        patch("app.api.web.google_oauth_adapter.exchange_code", new_callable=AsyncMock) as mock_ex,
        patch(
            "app.api.web.google_oauth_adapter.fetch_user_info", new_callable=AsyncMock
        ) as mock_info,
    ):
        mock_ex.return_value = {"access_token": "valid_oauth_access_token"}
        mock_info.return_value = user_info

        res_callback = await async_client.get(
            "/auth/callback/google?code=valid_code", follow_redirects=False
        )
        assert res_callback.status_code == 302
        assert res_callback.headers["location"] == "/"
        assert "session_token" in res_callback.cookies

        # Acessa a home com o cookie gerado
        res_home = await async_client.get("/", cookies=res_callback.cookies)
        assert res_home.status_code == 200
        assert "Real Google User" in res_home.text
        assert "logout-btn" in res_home.text

    # 2. Usuário existente logando novamente (reutilização/atualização de perfil)
    with (
        patch("app.api.web.google_oauth_adapter.exchange_code", new_callable=AsyncMock) as mock_ex,
        patch(
            "app.api.web.google_oauth_adapter.fetch_user_info", new_callable=AsyncMock
        ) as mock_info,
    ):
        mock_ex.return_value = {"access_token": "valid_oauth_access_token_2"}
        mock_info.return_value = user_info

        res_callback2 = await async_client.get(
            "/auth/callback/google?code=another_valid_code", follow_redirects=False
        )
        assert res_callback2.status_code == 302
        assert res_callback2.headers["location"] == "/"


def test_set_session_cookie_environment_behavior(monkeypatch):
    """Valida a emissão segura de cookies dependente do ambiente (Secure flag em prod/staging)."""
    # 1. Em desenvolvimento/local: secure deve ser False para funcionar em http://localhost
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    res_dev = Response()
    _set_session_cookie(res_dev, session_token="token_dev")
    cookie_header_dev = res_dev.headers.get("set-cookie", "")
    assert "session_token=token_dev" in cookie_header_dev
    assert "HttpOnly" in cookie_header_dev
    assert "SameSite=lax" in cookie_header_dev
    assert "secure" not in cookie_header_dev.lower()

    # 2. Em produção: secure deve ser True
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    res_prod = Response()
    _set_session_cookie(res_prod, session_token="token_prod")
    cookie_header_prod = res_prod.headers.get("set-cookie", "")
    assert "session_token=token_prod" in cookie_header_prod
    assert "HttpOnly" in cookie_header_prod
    assert "Secure" in cookie_header_prod

    # 3. Em staging: secure deve ser True
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    res_staging = Response()
    _set_session_cookie(res_staging, session_token="token_staging")
    cookie_header_staging = res_staging.headers.get("set-cookie", "")
    assert "Secure" in cookie_header_staging


@pytest.mark.asyncio
async def test_google_callback_direct():
    """Valida execução direta do handler google_callback delegando para AuthService."""
    auth_service_mock = MagicMock(spec=AuthService)
    user_mock = User(id=uuid.uuid4(), email="test@google.com")
    auth_service_mock.authenticate_oauth_user = AsyncMock(
        return_value=(user_mock, "jwt_token_google")
    )

    resp = await google_callback(
        request=MagicMock(spec=Request),
        code="valid_code",
        auth_service=auth_service_mock,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"
    assert "session_token=jwt_token_google" in resp.headers.get("set-cookie", "")
    auth_service_mock.authenticate_oauth_user.assert_awaited_once()

    # Cenário de OAuthError levantado pelo AuthService
    auth_service_mock.authenticate_oauth_user = AsyncMock(side_effect=OAuthError("OAuth failed"))
    resp_err = await google_callback(
        request=MagicMock(spec=Request),
        code="bad_code",
        auth_service=auth_service_mock,
    )
    assert resp_err.status_code == 302
    assert resp_err.headers["location"] == "/?auth_error=oauth_failed"
