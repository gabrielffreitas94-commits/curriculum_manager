"""Testes unitários do serviço de telemetria e rastreamento de tokens (TokenService)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import User, UserSettings
from app.services.token_service import (
    DEFAULT_DAILY_TOKEN_LIMIT,
    get_time_until_utc_reset,
    get_user_token_usage,
    record_token_usage,
)


@pytest.fixture
def resume_user() -> User:
    """Fixture com usuário para teste de rastreamento de tokens."""
    return User(
        id=uuid.uuid4(),
        firebase_uid="token_tester_uid",
        email="token_tester@thothcvs.ai",
        full_name="Token Tester",
    )


@pytest.mark.asyncio
async def test_record_token_usage_creates_settings_and_increments(
    db_session: AsyncSession,
    resume_user: User,
) -> None:
    """Valida criação inicial de UserSettings e incremento de consumo de tokens."""
    db_session.add(resume_user)
    await db_session.flush()

    settings = await record_token_usage(
        db=db_session,
        user=resume_user,
        tokens_used=1500,
    )

    today = datetime.now(UTC).date()
    assert settings.user_id == resume_user.id
    assert settings.tokens_used_today == 1500
    assert settings.requests_used_today == 1
    assert settings.tokens_used_total == 1500
    assert settings.last_token_reset_date == today


@pytest.mark.asyncio
async def test_record_token_usage_accumulates_same_day(
    db_session: AsyncSession,
    resume_user: User,
) -> None:
    """Valida acumulação de múltiplos consumos de tokens no mesmo dia."""
    db_session.add(resume_user)
    await db_session.flush()

    today = datetime.now(UTC).date()
    existing_settings = UserSettings(
        user_id=resume_user.id,
        tokens_used_today=1000,
        requests_used_today=2,
        tokens_used_total=5000,
        last_token_reset_date=today,
    )
    db_session.add(existing_settings)
    await db_session.commit()

    updated = await record_token_usage(
        db=db_session,
        user=resume_user,
        tokens_used=500,
    )

    assert updated.tokens_used_today == 1500
    assert updated.requests_used_today == 3
    assert updated.tokens_used_total == 5500
    assert updated.last_token_reset_date == today


@pytest.mark.asyncio
async def test_record_token_usage_resets_on_new_day(
    db_session: AsyncSession,
    resume_user: User,
) -> None:
    """Valida que mudança de data zera o contador diário e mantém o total acumulado."""
    db_session.add(resume_user)
    await db_session.flush()

    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    existing_settings = UserSettings(
        user_id=resume_user.id,
        tokens_used_today=3000,
        requests_used_today=5,
        tokens_used_total=10000,
        last_token_reset_date=yesterday,
    )
    db_session.add(existing_settings)
    await db_session.commit()

    today = datetime.now(UTC).date()
    updated = await record_token_usage(
        db=db_session,
        user=resume_user,
        tokens_used=800,
    )

    assert updated.tokens_used_today == 800
    assert updated.requests_used_today == 1
    assert updated.tokens_used_total == 10800
    assert updated.last_token_reset_date == today


@pytest.mark.asyncio
async def test_record_token_usage_ignores_non_positive_tokens(
    db_session: AsyncSession,
    resume_user: User,
) -> None:
    """Valida que chamadas com 0 ou tokens negativos não alteram contadores."""
    db_session.add(resume_user)
    await db_session.flush()

    today = datetime.now(UTC).date()
    existing_settings = UserSettings(
        user_id=resume_user.id,
        tokens_used_today=500,
        requests_used_today=1,
        tokens_used_total=500,
        last_token_reset_date=today,
    )
    db_session.add(existing_settings)
    await db_session.commit()

    res = await record_token_usage(
        db=db_session,
        user=resume_user,
        tokens_used=0,
    )

    assert res.tokens_used_today == 500
    assert res.requests_used_today == 1
    assert res.tokens_used_total == 500


@pytest.mark.asyncio
async def test_get_user_token_usage_without_settings(
    db_session: AsyncSession,
) -> None:
    """Valida retorno com valores zerados para usuário sem UserSettings."""
    fake_user_id = uuid.uuid4()
    data = await get_user_token_usage(db_session, fake_user_id)

    assert data["tokens_used_today"] == 0
    assert data["requests_used_today"] == 0
    assert data["tokens_used_total"] == 0
    assert data["formatted_tokens_today"] == "0"
    assert data["formatted_tokens_total"] == "0"


@pytest.mark.asyncio
async def test_get_user_token_usage_with_expired_date(
    db_session: AsyncSession,
    resume_user: User,
) -> None:
    """Valida que dia expirado retorna 0 para tokens hoje mas mantém o total acumulado."""
    db_session.add(resume_user)
    await db_session.flush()

    past_date = datetime.now(UTC).date() - timedelta(days=2)
    settings = UserSettings(
        user_id=resume_user.id,
        tokens_used_today=2500,
        requests_used_today=3,
        tokens_used_total=12500,
        last_token_reset_date=past_date,
    )
    db_session.add(settings)
    await db_session.commit()

    data = await get_user_token_usage(db_session, resume_user.id)

    assert data["tokens_used_today"] == 0
    assert data["requests_used_today"] == 0
    assert data["tokens_used_total"] == 12500
    assert data["formatted_tokens_today"] == "0"
    assert data["formatted_tokens_total"] == "12.500"


@pytest.mark.asyncio
async def test_get_user_token_usage_current_day_formatted(
    db_session: AsyncSession,
    resume_user: User,
) -> None:
    """Valida formatação numérica brasileira para tokens do dia e total."""
    db_session.add(resume_user)
    await db_session.flush()

    today = datetime.now(UTC).date()
    settings = UserSettings(
        user_id=resume_user.id,
        tokens_used_today=3420,
        requests_used_today=4,
        tokens_used_total=25400,
        last_token_reset_date=today,
    )
    db_session.add(settings)
    await db_session.commit()

    data = await get_user_token_usage(db_session, resume_user.id)

    assert data["tokens_used_today"] == 3420
    assert data["requests_used_today"] == 4
    assert data["tokens_used_total"] == 25400
    assert data["formatted_tokens_today"] == "3.420"
    assert data["formatted_tokens_total"] == "25.400"


def test_get_time_until_utc_reset_deterministic() -> None:
    """Valida cálculo determinístico de segundos e formatação até o reset às 00:00 UTC."""
    fixed_now = datetime(2026, 9, 29, 18, 30, 0, tzinfo=UTC)
    seconds, formatted = get_time_until_utc_reset(fixed_now)

    # Das 18:30 às 00:00 UTC são 5 horas e 30 minutos = 5 * 3600 + 30 * 60 = 19.800s
    assert seconds == 19800
    assert formatted == "5h 30m"


@pytest.mark.asyncio
async def test_get_user_token_usage_includes_daily_limit_and_reset_metadata(
    db_session: AsyncSession,
    resume_user: User,
) -> None:
    """Valida que o payload de consumo de tokens inclui limite diário, percentual e metadados de reset."""
    db_session.add(resume_user)
    await db_session.flush()

    today = datetime.now(UTC).date()
    settings = UserSettings(
        user_id=resume_user.id,
        tokens_used_today=50000,
        requests_used_today=10,
        tokens_used_total=150000,
        last_token_reset_date=today,
    )
    db_session.add(settings)
    await db_session.commit()

    data = await get_user_token_usage(db_session, resume_user.id)

    assert data["tokens_limit_daily"] == DEFAULT_DAILY_TOKEN_LIMIT
    assert data["formatted_tokens_limit_daily"] == "1.000.000"
    assert data["tokens_percent_used"] == 5.0
    assert data["reset_time_utc"] == "00:00 UTC"
    assert data["seconds_until_reset"] >= 0
    assert "h " in data["formatted_time_until_reset"]

