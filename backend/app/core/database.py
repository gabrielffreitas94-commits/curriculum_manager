"""Configuração da engine de banco de dados assíncrona e gerenciamento de sessões.

Estabelece o pooling de conexões do SQLAlchemy 2.0 compatível com PostgreSQL
no Supabase e SQLite em memória para testes e desenvolvimento leve.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Engine assíncrona central da aplicação
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

# Fábrica de sessões assíncronas isoladas
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency do FastAPI para fornecer uma sessão assíncrona por requisição.

    Garante commit automático em caso de sucesso e rollback transacional
    completo caso ocorra qualquer exceção não tratada na camada de roteamento.

    Yields:
        AsyncSession: Sessão transacional aberta conectada ao banco de dados.

    Raises:
        Exception: Re-lança qualquer exceção levantada na execução do endpoint.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
