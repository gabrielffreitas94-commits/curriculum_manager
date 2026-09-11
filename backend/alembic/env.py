"""Configuração do ambiente de migrações assíncronas com Alembic.

Conecta ao banco de dados via SQLAlchemy 2.0 assíncrono e inspeciona
o Base.metadata unificado contendo a totalidade das entidades de domínio.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importa explicitamente todos os modelos para registro completo dos metadados
import app.domain.models  # noqa: F401
from alembic import context
from app.core.config import settings
from app.domain.base import Base

config = context.config

# Configuração de logging do Alembic
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Define os metadados alvo para autogenerate das migrações
target_metadata = Base.metadata

# Sobrescreve dinamicamente a URL com a variável de ambiente configurada
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    """Executa migrações em modo offline (sem conexão ativa com o banco).

    Configura o contexto apenas com a URL e gera as instruções SQL
    diretamente para a saída do script.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Executa as operações de migração síncronas dentro da conexão assíncrona.

    Args:
        connection: Conexão ativa com o banco de dados SQLAlchemy.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Cria a engine assíncrona temporária e executa as migrações online."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Ponto de entrada para execução de migrações no modo online."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
