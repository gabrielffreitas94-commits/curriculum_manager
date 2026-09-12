"""Testes unitários para UserService e ciclo de vida de contas de usuários (LGPD Art. 18).

Cobre a revogação de tokens no FirebaseAuthAdapter, a execução atômica do UserService
e a fábrica de dependências get_user_service.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.firebase_auth_adapter import FirebaseAuthAdapter
from app.api.v1.deps import get_user_service
from app.domain.models import User
from app.ports.auth_port import AuthError
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_revoke_user_tokens_success() -> None:
    """Valida que revoke_user_tokens conclui com sucesso para um UID válido."""
    adapter = FirebaseAuthAdapter()
    result = await adapter.revoke_user_tokens("valid_firebase_uid_123")
    assert result is None


@pytest.mark.asyncio
async def test_revoke_user_tokens_empty_uid_raises_auth_error() -> None:
    """Garante fail-closed lançando AuthError se o UID for vazio ou espaços."""
    adapter = FirebaseAuthAdapter()

    with pytest.raises(AuthError, match="Identificador do usuário inválido"):
        await adapter.revoke_user_tokens("")

    with pytest.raises(AuthError, match="Identificador do usuário inválido"):
        await adapter.revoke_user_tokens("   ")


@pytest.mark.asyncio
async def test_user_service_delete_user_account_flow() -> None:
    """Valida a orquestração do UserService na remoção atômica e revogação de tokens."""
    mock_db = AsyncMock()
    mock_auth_port = AsyncMock()

    service = UserService(db=mock_db, auth_port=mock_auth_port)

    test_user = User(
        id=uuid.uuid4(),
        firebase_uid="firebase_victim_uid_999",
        email="victim@thothcvs.ai",
        full_name="Victim User",
    )

    await service.delete_user_account(test_user)

    # 1. Deve executar a deleção de PromptSkills customizadas
    assert mock_db.execute.call_count == 1

    # 2. Deve deletar a entidade User
    mock_db.delete.assert_called_once_with(test_user)

    # 3. Deve commitar a transação de banco de dados
    mock_db.commit.assert_called_once()

    # 4. Deve revogar as credenciais do usuário na porta de autenticação
    mock_auth_port.revoke_user_tokens.assert_called_once_with("firebase_victim_uid_999")


@pytest.mark.asyncio
async def test_get_user_service_dependency() -> None:
    """Valida a fábrica de injeção de dependência get_user_service do FastAPI."""
    mock_db = MagicMock()
    service = await get_user_service(db=mock_db)

    assert isinstance(service, UserService)
    assert service.db is mock_db
    assert isinstance(service.auth_port, FirebaseAuthAdapter)
