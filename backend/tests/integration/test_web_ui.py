"""Testes de integração para a interface Web servida com HTMX e Jinja2."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from httpx import AsyncClient

from app.api.web import (
    create_session_jwt,
    get_authenticated_web_user,
    google_callback,
    login_google,
    login_linkedin,
)
from app.domain.models import User
from app.ports.oauth_port import OAuthError, OAuthUserInfo


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
async def test_google_login_flow(async_client: AsyncClient):
    """Valida fluxo de login social com Google, persistência e atualização da interface."""
    # 1. Primeiro login com Google (cria novo usuário)
    res_login1 = await async_client.post("/auth/login/google")
    assert res_login1.status_code == 200
    assert res_login1.headers.get("HX-Refresh") == "true"
    assert "session_token" in res_login1.cookies
    assert res_login1.cookies.get("session_token") == "mock_google_user"

    # 2. Acessa a home e verifica se o usuário está autenticado no header
    res_home = await async_client.get("/", cookies=res_login1.cookies)
    assert res_home.status_code == 200
    assert "Usuário Google" in res_home.text
    assert "logout-btn" in res_home.text

    # 3. Segundo login com Google (recupera usuário existente)
    res_login2 = await async_client.post("/auth/login/google")
    assert res_login2.status_code == 200
    assert res_login2.headers.get("HX-Refresh") == "true"


@pytest.mark.asyncio
async def test_linkedin_login_flow(async_client: AsyncClient):
    """Valida fluxo de login social com LinkedIn, persistência e atualização da interface."""
    # 1. Primeiro login com LinkedIn (cria novo usuário)
    res_login1 = await async_client.post("/auth/login/linkedin")
    assert res_login1.status_code == 200
    assert res_login1.headers.get("HX-Refresh") == "true"
    assert "session_token" in res_login1.cookies
    assert res_login1.cookies.get("session_token") == "mock_linkedin_user"

    # 2. Acessa a home e verifica se o usuário está autenticado no header
    res_home = await async_client.get("/", cookies=res_login1.cookies)
    assert res_home.status_code == 200
    assert "Usuário LinkedIn" in res_home.text
    assert "logout-btn" in res_home.text

    # 3. Segundo login com LinkedIn (recupera usuário existente)
    res_login2 = await async_client.post("/auth/login/linkedin")
    assert res_login2.status_code == 200
    assert res_login2.headers.get("HX-Refresh") == "true"


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
    """Valida resolução direta de usuário autenticado na Web UI com mock de sessão DB."""
    # 1. Sem cookie / vazio
    req_no_cookie = MagicMock(spec=Request)
    req_no_cookie.cookies = {}
    db_mock = MagicMock()
    user_none = await get_authenticated_web_user(req_no_cookie, db_mock)
    assert user_none is None

    # 2. Com token válido e usuário encontrado no banco
    req_with_cookie = MagicMock(spec=Request)
    req_with_cookie.cookies = {"session_token": "mock_direct_test_user"}
    user_mock = User(
        id=uuid.uuid4(), firebase_uid="mock_uid_mock_direct_test_user", email="direct@test.com"
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = user_mock
    db_mock.execute = AsyncMock(return_value=mock_res)

    user_found = await get_authenticated_web_user(req_with_cookie, db_mock)
    assert user_found == user_mock
    assert user_found.email == "direct@test.com"


@pytest.mark.asyncio
async def test_social_login_direct():
    """Valida execução direta dos handlers de login social com Google e LinkedIn."""
    # 1. Google - novo usuário
    db_mock = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db_mock.execute = AsyncMock(return_value=mock_res)
    db_mock.flush = AsyncMock()
    db_mock.commit = AsyncMock()

    resp_google_new = await login_google(request=MagicMock(spec=Request), db=db_mock)
    assert resp_google_new.status_code == 200
    assert resp_google_new.headers.get("HX-Refresh") == "true"
    assert "session_token" in resp_google_new.headers.get("set-cookie", "")

    # 2. Google - usuário já existente
    user_existing = User(
        id=uuid.uuid4(),
        firebase_uid="mock_uid_mock_google_user",
        email="usuario.google@exemplo.com",
    )
    mock_res.scalar_one_or_none.return_value = user_existing
    resp_google_exist = await login_google(request=MagicMock(spec=Request), db=db_mock)
    assert resp_google_exist.status_code == 200

    # 3. LinkedIn - novo usuário
    mock_res.scalar_one_or_none.return_value = None
    resp_linkedin_new = await login_linkedin(request=MagicMock(spec=Request), db=db_mock)
    assert resp_linkedin_new.status_code == 200
    assert resp_linkedin_new.headers.get("HX-Refresh") == "true"
    assert "session_token" in resp_linkedin_new.headers.get("set-cookie", "")

    # 4. LinkedIn - usuário já existente
    user_li_existing = User(
        id=uuid.uuid4(),
        firebase_uid="mock_uid_mock_linkedin_user",
        email="usuario.linkedin@exemplo.com",
    )
    mock_res.scalar_one_or_none.return_value = user_li_existing
    resp_linkedin_exist = await login_linkedin(request=MagicMock(spec=Request), db=db_mock)
    assert resp_linkedin_exist.status_code == 200


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
        assert res.headers["location"] == "/?auth_error=invalid_token"


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


@pytest.mark.asyncio
async def test_get_authenticated_web_user_jwt_branches():
    """Valida branches de validação de token JWT de sessão em get_authenticated_web_user."""
    # 1. JWT válido com usuário no banco
    valid_jwt = create_session_jwt(uid="google_test_sub", email="test@gmail.com")
    req = MagicMock(spec=Request)
    req.cookies = {"session_token": valid_jwt}

    db_mock = MagicMock()
    mock_res = MagicMock()
    user_mock = User(id=uuid.uuid4(), firebase_uid="google_test_sub", email="test@gmail.com")
    mock_res.scalar_one_or_none.return_value = user_mock
    db_mock.execute = AsyncMock(return_value=mock_res)

    found = await get_authenticated_web_user(req, db_mock)
    assert found == user_mock

    # 2. JWT válido mas usuário não existe no banco
    mock_res.scalar_one_or_none.return_value = None
    not_found = await get_authenticated_web_user(req, db_mock)
    assert not_found is None


@pytest.mark.asyncio
async def test_google_callback_direct():
    """Valida execução direta do handler google_callback para novos e existentes usuários."""
    # 1. Novo usuário (criação de User e UserSettings)
    db_mock_new = MagicMock()
    mock_res_new = MagicMock()
    mock_res_new.scalar_one_or_none.return_value = None
    db_mock_new.execute = AsyncMock(return_value=mock_res_new)
    db_mock_new.flush = AsyncMock()
    db_mock_new.commit = AsyncMock()

    user_info_new = OAuthUserInfo(sub="new_123", email="novo@gmail.com", full_name="Novo Usuário")

    with (
        patch("app.api.web.google_oauth_adapter.exchange_code", new_callable=AsyncMock) as mock_ex,
        patch(
            "app.api.web.google_oauth_adapter.fetch_user_info", new_callable=AsyncMock
        ) as mock_info,
    ):
        mock_ex.return_value = {"access_token": "token_ok"}
        mock_info.return_value = user_info_new

        resp_new = await google_callback(
            request=MagicMock(spec=Request),
            code="test_code_new",
            db=db_mock_new,
        )
        assert resp_new.status_code == 302
        assert "session_token" in resp_new.headers.get("set-cookie", "")

    # 2. Usuário existente (atualização de perfil)
    db_mock = MagicMock()
    mock_res = MagicMock()
    user_existing = User(
        id=uuid.uuid4(), firebase_uid="google_999", email="existing@gmail.com", full_name=""
    )
    mock_res.scalar_one_or_none.return_value = user_existing
    db_mock.execute = AsyncMock(return_value=mock_res)
    db_mock.commit = AsyncMock()

    user_info = OAuthUserInfo(sub="999", email="existing@gmail.com", full_name="Nome Atualizado")

    with (
        patch("app.api.web.google_oauth_adapter.exchange_code", new_callable=AsyncMock) as mock_ex,
        patch(
            "app.api.web.google_oauth_adapter.fetch_user_info", new_callable=AsyncMock
        ) as mock_info,
    ):
        mock_ex.return_value = {"access_token": "token_ok"}
        mock_info.return_value = user_info

        resp = await google_callback(
            request=MagicMock(spec=Request),
            code="test_code",
            db=db_mock,
        )
        assert resp.status_code == 302
        assert "session_token" in resp.headers.get("set-cookie", "")
        assert user_existing.full_name == "Nome Atualizado"
