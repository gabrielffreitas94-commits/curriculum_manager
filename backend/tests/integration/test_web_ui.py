"""Testes de integração para a interface Web servida com HTMX e Jinja2."""

import pytest
from httpx import AsyncClient


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

