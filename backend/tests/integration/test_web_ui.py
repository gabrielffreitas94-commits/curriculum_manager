"""Testes de integração para a interface Web servida com HTMX e Jinja2."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from httpx import AsyncClient

from app.api.web import get_authenticated_web_user
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
    """Valida renderização do fragmento HTML do modal de login com Google, LinkedIn e E-mail."""
    response = await async_client.get("/auth/modal")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    content = response.text

    assert "Acessar Plataforma" in content
    assert "btn-login-google" in content
    assert "Continuar com o Google" in content
    assert "btn-login-linkedin" in content
    assert "Continuar com o LinkedIn" in content
    assert "login-email" in content
    assert "login-password" in content
    assert "btn-submit-email-login" in content
    assert "closeModal" in content


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
async def test_auth_views_render_successfully(async_client: AsyncClient):
    """Valida renderização dos cards parciais para alternância fluida no modal via HTMX."""
    # 1. Login card view
    res_login = await async_client.get("/auth/login-view")
    assert res_login.status_code == 200
    assert "auth-modal-card" in res_login.text
    assert "Continuar com o Google" in res_login.text
    assert "Cadastre-se gratuitamente" in res_login.text

    # 2. Register card view
    res_reg = await async_client.get("/auth/register-view")
    assert res_reg.status_code == 200
    assert "auth-modal-card" in res_reg.text
    assert "Criar Conta" in res_reg.text
    assert "reg-name" in res_reg.text
    assert "reg-password-confirm" in res_reg.text

    # 3. Forgot password card view
    res_fp = await async_client.get("/auth/forgot-password-view")
    assert res_fp.status_code == 200
    assert "auth-modal-card" in res_fp.text
    assert "Recuperar Senha" in res_fp.text
    assert "forgot-email" in res_fp.text


@pytest.mark.asyncio
async def test_register_submit_validation_errors(async_client: AsyncClient):
    """Valida tratamento de erros de validação no formulário de cadastro."""
    # Campos vazios
    r1 = await async_client.post("/auth/register", data={"full_name": "", "email": "", "password": "", "password_confirm": ""})
    assert r1.status_code == 200
    assert "Todos os campos são obrigatórios" in r1.text

    # Senhas divergentes
    r2 = await async_client.post(
        "/auth/register",
        data={"full_name": "Ana Silva", "email": "ana@example.com", "password": "password123", "password_confirm": "mismatch456"}
    )
    assert r2.status_code == 200
    assert "As senhas informadas não coincidem" in r2.text

    # Senha curta (< 6)
    r3 = await async_client.post(
        "/auth/register",
        data={"full_name": "Ana Silva", "email": "ana@example.com", "password": "123", "password_confirm": "123"}
    )
    assert r3.status_code == 200
    assert "A senha deve conter no mínimo 6 caracteres" in r3.text


@pytest.mark.asyncio
async def test_register_login_and_logout_flow(async_client: AsyncClient):
    """Valida fluxo de cadastro de novo usuário, login recorrente e logout com cookies e Header."""
    test_email = "dev_ui_user@test.com"
    test_name = "Dev UI User"

    # 1. Cadastro com sucesso
    res_reg = await async_client.post(
        "/auth/register",
        data={
            "full_name": test_name,
            "email": test_email,
            "password": "strongPassword123",
            "password_confirm": "strongPassword123",
        },
    )
    assert res_reg.status_code == 200
    assert res_reg.headers.get("HX-Refresh") == "true"
    assert "session_token" in res_reg.cookies

    # 2. Cadastro duplicado deve retornar erro amigável
    res_dup = await async_client.post(
        "/auth/register",
        data={
            "full_name": test_name,
            "email": test_email,
            "password": "strongPassword123",
            "password_confirm": "strongPassword123",
        },
    )
    assert res_dup.status_code == 200
    assert "Este e-mail já está cadastrado" in res_dup.text

    # 3. Acessar página inicial autenticado
    res_home = await async_client.get("/", cookies=res_reg.cookies)
    assert res_home.status_code == 200
    assert test_name in res_home.text
    assert "logout-btn" in res_home.text

    # 4. Login com credenciais inválidas
    res_bad_login = await async_client.post(
        "/auth/login",
        data={"email": "nonexistent@test.com", "password": "wrongpassword"}
    )
    assert res_bad_login.status_code == 200
    assert "Credenciais inválidas" in res_bad_login.text

    # 5. Login com campos vazios
    res_empty_login = await async_client.post(
        "/auth/login",
        data={"email": "", "password": ""}
    )
    assert res_empty_login.status_code == 200
    assert "Informe o e-mail e a senha" in res_empty_login.text

    # 6. Login com sucesso
    res_good_login = await async_client.post(
        "/auth/login",
        data={"email": test_email, "password": "strongPassword123"}
    )
    assert res_good_login.status_code == 200
    assert res_good_login.headers.get("HX-Refresh") == "true"
    assert "session_token" in res_good_login.cookies

    # 7. Logout
    res_logout = await async_client.post("/auth/logout")
    assert res_logout.status_code == 200
    assert res_logout.headers.get("HX-Refresh") == "true"


@pytest.mark.asyncio
async def test_forgot_password_submission(async_client: AsyncClient):
    """Valida solicitação de recuperação de senha com feedback visual."""
    # E-mail inválido
    r_bad = await async_client.post("/auth/forgot-password", data={"email": "invalid-email"})
    assert r_bad.status_code == 200
    assert "Informe um endereço de e-mail válido" in r_bad.text

    # E-mail válido
    r_ok = await async_client.post("/auth/forgot-password", data={"email": "user@example.com"})
    assert r_ok.status_code == 200
    assert "E-mail de recuperação enviado" in r_ok.text
    assert "user@example.com" in r_ok.text


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



