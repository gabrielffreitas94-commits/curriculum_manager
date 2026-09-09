"""Fixtures globais para a suíte de testes do ThothCVs AI Backend.

Configura o cliente HTTP assíncrono para testes contra a aplicação FastAPI
e gerencia o ciclo de vida de testes isolados com banco de dados em memória.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domain.base import Base
from app.main import app

# Engine isolada para testes usando SQLite assíncrono em memória
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def async_engine():
    """Cria a engine assíncrona isolada em memória para a suíte de testes."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Fornece uma sessão de banco assíncrona isolada para cada teste unitário/integração.

    Yields:
        AsyncSession: Sessão transacional com rollback automático.
    """
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Cria e fornece um cliente HTTP assíncrono conectado à aplicação FastAPI.

    Yields:
        AsyncClient: Instância do cliente HTTP para disparo de requisições de teste.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
