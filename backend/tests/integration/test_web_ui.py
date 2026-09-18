"""Testes de integração para a interface Web servida com HTMX e Jinja2."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from httpx import AsyncClient

from app.api.web import get_authenticated_web_user, login_google, login_linkedin
from app.domain.models import User


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
    user_mock = User(id=uuid.uuid4(), firebase_uid="mock_uid_mock_direct_test_user", email="direct@test.com")
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
    user_existing = User(id=uuid.uuid4(), firebase_uid="mock_uid_mock_google_user", email="usuario.google@exemplo.com")
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
    user_li_existing = User(id=uuid.uuid4(), firebase_uid="mock_uid_mock_linkedin_user", email="usuario.linkedin@exemplo.com")
    mock_res.scalar_one_or_none.return_value = user_li_existing
    resp_linkedin_exist = await login_linkedin(request=MagicMock(spec=Request), db=db_mock)
    assert resp_linkedin_exist.status_code == 200




