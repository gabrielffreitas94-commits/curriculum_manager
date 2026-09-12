"""Testes de integração para o CorrelationMiddleware e propagação do header X-Correlation-ID."""

import uuid

import pytest
from fastapi import Request, Response
from httpx import AsyncClient

from app.core.correlation_middleware import CorrelationMiddleware
from app.core.telemetry import get_correlation_id


@pytest.mark.asyncio
async def test_correlation_middleware_generates_id_when_missing(async_client: AsyncClient):
    """Valida geração e injeção do header X-Correlation-ID caso ausente na requisição."""
    response = await async_client.get("/healthz")

    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers

    correlation_id = response.headers["X-Correlation-ID"]
    # Valida formato UUIDv4
    parsed_uuid = uuid.UUID(correlation_id)
    assert str(parsed_uuid) == correlation_id


@pytest.mark.asyncio
async def test_correlation_middleware_preserves_client_provided_id(async_client: AsyncClient):
    """Valida propagação fiel do X-Correlation-ID fornecido pelo cliente (frontend)."""
    custom_id = "client-trace-abc-12345"
    response = await async_client.get("/healthz", headers={"X-Correlation-ID": custom_id})

    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == custom_id


@pytest.mark.asyncio
async def test_correlation_middleware_returns_header_on_404(async_client: AsyncClient):
    """Valida retorno do header X-Correlation-ID em respostas de erro (404 Not Found)."""
    response = await async_client.get("/api/v1/non-existent-endpoint")

    assert response.status_code == 404
    assert "X-Correlation-ID" in response.headers
    assert len(response.headers["X-Correlation-ID"]) > 0


@pytest.mark.asyncio
async def test_correlation_middleware_handles_500_response():
    """Valida registro e injeção de correlation ID em respostas com status 500 (Internal Error)."""
    middleware = CorrelationMiddleware(app=None)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/server-error",
        "headers": [(b"host", b"testserver")],
    }
    request = Request(scope)

    async def call_next_500(req: Request) -> Response:
        return Response(status_code=500)

    response = await middleware.dispatch(request, call_next_500)
    assert response.status_code == 500
    assert "X-Correlation-ID" in response.headers


@pytest.mark.asyncio
async def test_correlation_middleware_handles_unhandled_exception():
    """Valida que exceções não tratadas são logadas e o contexto de telemetria é limpo."""
    middleware = CorrelationMiddleware(app=None)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/crash-route",
        "headers": [(b"host", b"testserver")],
    }
    request = Request(scope)

    async def call_next_crash(req: Request):
        raise RuntimeError("Simulated unhandled exception")

    with pytest.raises(RuntimeError, match="Simulated unhandled exception"):
        await middleware.dispatch(request, call_next_crash)

    # Contexto assíncrono deve ter sido devidamente limpo no bloco except
    assert get_correlation_id() is None
