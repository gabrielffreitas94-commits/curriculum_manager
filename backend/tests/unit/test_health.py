"""Testes unitários para as rotas de diagnóstico e verificação de saúde (Liveness e Readiness).

Valida a conformidade dos endpoints com os padrões do Google Cloud Run.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz_liveness_probe(async_client: AsyncClient) -> None:
    """Verifica se o endpoint de liveness probe (/healthz) retorna status 200 OK.

    Args:
        async_client: Cliente HTTP assíncrono injetado pela fixture.

    Business Rules:
        - O probe deve responder com status 200 e payload contendo "healthy".
    """
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "thothcvs-backend"


@pytest.mark.asyncio
async def test_ready_readiness_probe(async_client: AsyncClient) -> None:
    """Verifica se o endpoint de readiness probe (/ready) responde adequadamente.

    Args:
        async_client: Cliente HTTP assíncrono injetado pela fixture.

    Business Rules:
        - O probe deve responder com status 200 indicando prontidão para receber tráfego.
    """
    response = await async_client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
