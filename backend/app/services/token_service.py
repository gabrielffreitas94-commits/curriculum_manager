"""Serviço de telemetria e rastreamento de consumo de tokens (LLMOps)."""

from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models import User, UserSettings

logger = get_logger("token_service")

# Cota padrão diária no Free Tier do Google Gemini (1 milhão de tokens)
DEFAULT_DAILY_TOKEN_LIMIT: int = 1_000_000


def get_time_until_utc_reset(now: datetime | None = None) -> tuple[int, str]:
    """Calcula os segundos restantes e formatação textual amigável até o próximo reset à 00:00 UTC.

    Args:
        now: Timestamp atual em UTC (opcional, para testes determinísticos).

    Returns:
        Tupla com (segundos_restantes, string_formatada_ex_7h_32m).
    """
    current_time = now or datetime.now(UTC)
    tomorrow_midnight = datetime.combine(
        current_time.date() + timedelta(days=1),
        time.min,
        tzinfo=UTC,
    )
    seconds_remaining = max(0, int((tomorrow_midnight - current_time).total_seconds()))
    hours = seconds_remaining // 3600
    minutes = (seconds_remaining % 3600) // 60
    return seconds_remaining, f"{hours}h {minutes:02d}m"


async def record_token_usage(
    db: AsyncSession,
    user: User,
    tokens_used: int,
) -> UserSettings:
    """Atualiza de forma atômica e transacional o consumo de tokens e requisições do usuário.

    Args:
        db: Sessão ativa do banco de dados relacional.
        user: Entidade de usuário proprietário da requisição.
        tokens_used: Quantidade de tokens reportada pelo provedor de IA.

    Returns:
        UserSettings: Entidade atualizada com os novos totais.
    """
    stmt = select(UserSettings).where(UserSettings.user_id == user.id)
    res = await db.execute(stmt)
    user_settings = res.scalar_one_or_none()

    if not user_settings:
        user_settings = UserSettings(
            user_id=user.id,
            tokens_used_today=0,
            requests_used_today=0,
            tokens_used_total=0,
        )
        db.add(user_settings)

    if tokens_used <= 0:
        return user_settings

    today = datetime.now(UTC).date()
    if user_settings.last_token_reset_date != today:
        user_settings.tokens_used_today = 0
        user_settings.requests_used_today = 0
        user_settings.last_token_reset_date = today

    user_settings.tokens_used_today = (user_settings.tokens_used_today or 0) + tokens_used
    user_settings.requests_used_today = (user_settings.requests_used_today or 0) + 1
    user_settings.tokens_used_total = (user_settings.tokens_used_total or 0) + tokens_used
    user_settings.updated_at = datetime.now(UTC)

    await db.commit()

    logger.info(
        "token_usage_recorded",
        user_id=str(user.id),
        tokens_added=tokens_used,
        tokens_used_today=user_settings.tokens_used_today,
        requests_used_today=user_settings.requests_used_today,
    )

    return user_settings


async def get_user_token_usage(
    db: AsyncSession,
    user_id: Any,
) -> dict[str, Any]:
    """Retorna os dados consolidados de consumo de tokens do usuário.

    Args:
        db: Sessão ativa do banco de dados relacional.
        user_id: UUID do usuário.

    Returns:
        Dicionário com métricas formatadas de tokens diários, limites, tempo de reset e totais.
    """
    stmt = select(UserSettings).where(UserSettings.user_id == user_id)
    res = await db.execute(stmt)
    settings = res.scalar_one_or_none()

    today = datetime.now(UTC).date()
    tokens_today = 0
    requests_today = 0
    tokens_total = 0

    if settings:
        if settings.last_token_reset_date == today:
            tokens_today = settings.tokens_used_today
            requests_today = settings.requests_used_today
        tokens_total = settings.tokens_used_total

    formatted_today = f"{tokens_today:,}".replace(",", ".")
    formatted_total = f"{tokens_total:,}".replace(",", ".")

    seconds_until_reset, formatted_time_until_reset = get_time_until_utc_reset()
    tokens_limit_daily = DEFAULT_DAILY_TOKEN_LIMIT
    tokens_percent_used = round(min(100.0, (tokens_today / tokens_limit_daily) * 100), 1)

    return {
        "tokens_used_today": tokens_today,
        "requests_used_today": requests_today,
        "tokens_used_total": tokens_total,
        "tokens_limit_daily": tokens_limit_daily,
        "tokens_percent_used": tokens_percent_used,
        "seconds_until_reset": seconds_until_reset,
        "formatted_tokens_today": formatted_today,
        "formatted_tokens_total": formatted_total,
        "formatted_tokens_limit_daily": f"{tokens_limit_daily:,}".replace(",", "."),
        "formatted_time_until_reset": formatted_time_until_reset,
        "reset_time_utc": "00:00 UTC",
    }
