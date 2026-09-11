"""Módulo base para o mapeamento relacional com SQLAlchemy 2.0.

Define a classe DeclarativeBase central e os mixins reutilizáveis para
auditoria de criação, atualização e soft delete (exclusão lógica).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Suporte híbrido JSON/JSONB: PostgreSQL usa JSONB com indexação GIN; SQLite usa JSON padrão
JSON_COMPAT = JSONB().with_variant(JSON, "sqlite")


class Base(DeclarativeBase):
    """Classe base declarativa de todos os modelos ORM da aplicação."""

    pass


class PrimaryKeyUUIDMixin:
    """Mixin que adiciona chave primária universal no formato UUID v4."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        sort_order=-10,
    )


class TimestampMixin:
    """Mixin que injeta carimbos de data/hora de criação e modificação.

    Attributes:
        created_at: Momento exato em que a linha foi inserida no banco (UTC).
        updated_at: Momento exato da última alteração de qualquer coluna (UTC).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class SoftDeleteMixin:
    """Mixin para exclusão lógica preservando o histórico de dados sensíveis.

    Attributes:
        deleted_at: Timestamp UTC da deleção. Se for None, o registro está ativo.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
