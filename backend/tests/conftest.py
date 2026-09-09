"""Fixtures globais para a suíte de testes do ThothCVs AI Backend.

Configura o cliente HTTP assíncrono para testes contra a aplicação FastAPI
e gerencia o ciclo de vida de testes isolados.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Cria e fornece um cliente HTTP assíncrono conectado à aplicação FastAPI.

    Yields:
        AsyncClient: Instância do cliente HTTP para disparo de requisições de teste.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
