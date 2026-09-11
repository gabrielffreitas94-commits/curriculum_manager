"""Testes unitários para o gerenciamento de sessões do banco de dados assíncrono."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.database import get_db_session


@pytest.mark.asyncio
async def test_get_db_session_success() -> None:
    """Testa se a generator fixture abre e comita a sessão com sucesso."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    mock_factory = MagicMock(return_value=mock_cm)

    with patch("app.core.database.async_session_factory", mock_factory):
        gen = get_db_session()
        session = await gen.asend(None)
        assert session is mock_session

        with pytest.raises(StopAsyncIteration):
            await gen.asend(None)

        mock_session.commit.assert_awaited_once()
        mock_session.rollback.assert_not_awaited()
        mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_db_session_rollback_on_error() -> None:
    """Testa se a sessão executa rollback e re-lança a exceção em caso de erro na rota."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    mock_factory = MagicMock(return_value=mock_cm)

    with patch("app.core.database.async_session_factory", mock_factory):
        gen = get_db_session()
        session = await gen.asend(None)
        assert session is mock_session

        with pytest.raises(RuntimeError, match="Simulated DB error"):
            await gen.athrow(RuntimeError("Simulated DB error"))

        mock_session.rollback.assert_awaited_once()
        mock_session.commit.assert_not_awaited()
        mock_session.close.assert_awaited_once()
