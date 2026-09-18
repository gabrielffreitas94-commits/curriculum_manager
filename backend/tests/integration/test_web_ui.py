"""Testes de integração para a interface Web servida com HTMX e Jinja2."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_welcome_page_renders_successfully(async_client: AsyncClient):
    """Valida renderização da página inicial de boas-vindas do ThothCVs AI com HTMX."""
    response = await async_client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    content = response.text

    # Asserções de conteúdo e estrutura HTML
    assert "Bem-vindo ao" in content
    assert "ThothCVs AI" in content
    assert "/static/js/htmx.min.js" in content
    assert 'hx-get="/htmx/ping"' in content
    assert 'hx-target="#htmx-demo-area"' in content
    assert "Adaptação Cirúrgica" in content
    assert "BYOK Seguro (ADR 0001)" in content


@pytest.mark.asyncio
async def test_htmx_ping_endpoint_returns_html_fragment(async_client: AsyncClient):
    """Valida que o endpoint HTMX /htmx/ping retorna fragmento HTML para substituição atômica."""
    response = await async_client.get("/htmx/ping")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    content = response.text

    assert "Reatividade HTMX Confirmada com Sucesso!" in content
    assert "healthy" in content
    assert "Status da Aplicação:" in content
    assert "Timestamp do Servidor:" in content


@pytest.mark.asyncio
async def test_static_htmx_file_is_served(async_client: AsyncClient):
    """Valida disponibilidade do asset estático local htmx.min.js montado em /static."""
    response = await async_client.get("/static/js/htmx.min.js")

    assert response.status_code == 200
    assert "htmx" in response.text
