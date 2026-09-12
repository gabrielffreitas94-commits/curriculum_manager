"""Gerenciador assíncrono de contexto de telemetria e rastreabilidade.

Armazena identificadores de correlação (correlation_id) e identidade de usuário
em variáveis de contexto assíncronas (ContextVar), permitindo propagação
transversal segura por todas as camadas da Arquitetura Hexagonal.
"""

from contextvars import ContextVar

# ContextVars assíncronas para propagação transversal de metadados
_correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id_ctx", default=None)
_user_id_ctx: ContextVar[str | None] = ContextVar("user_id_ctx", default=None)


def get_correlation_id() -> str | None:
    """Obtém o correlation_id associado ao ciclo de vida da requisição atual.

    Returns:
        str | None: Identificador de correlação ou None se fora do escopo de requisição.
    """
    return _correlation_id_ctx.get()


def set_correlation_id(correlation_id: str | None) -> None:
    """Define o correlation_id para o contexto da requisição atual.

    Args:
        correlation_id: Identificador único de correlação (geralmente UUIDv4).
    """
    _correlation_id_ctx.set(correlation_id)


def get_user_id() -> str | None:
    """Obtém o user_id autenticado associado ao contexto da requisição atual.

    Returns:
        str | None: ID do usuário ou None se anônimo / não autenticado.
    """
    return _user_id_ctx.get()


def set_user_id(user_id: str | None) -> None:
    """Define o user_id para o contexto da requisição atual.

    Args:
        user_id: Identificador do usuário (geralmente UUID ou UID Firebase).
    """
    _user_id_ctx.set(user_id)


def clear_telemetry_context() -> None:
    """Limpa todos os dados contextuais de telemetria da requisição."""
    _correlation_id_ctx.set(None)
    _user_id_ctx.set(None)
