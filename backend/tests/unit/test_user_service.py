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
    """
    VETOR DE AMEAÇA: LGPD Art. 18 / CWE-613 (Insufficient Session Expiration).
    Usuário encerra a conta, mas refresh tokens de autenticação previamente emitidos continuam
    válidos no provedor de identidade (IdP), permitindo sequestro e persistência de sessão.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    O adaptador DEVE revogar explicitamente todos os tokens ativos do usuário no Firebase Auth
    através de 'revoke_user_tokens(uid)', assegurando desativação imediata.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Um desenvolvedor ou IA pode remover a comunicação com o provedor para agilizar testes locais,
    deixando tokens órfãos e sessões ativas indefinidamente.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    A execução com UID legítimo conclui a revogação de tokens no provedor com sucesso.
    """
    adapter = FirebaseAuthAdapter()
    result = await adapter.revoke_user_tokens("valid_firebase_uid_123")
    assert result is None


@pytest.mark.asyncio
async def test_revoke_user_tokens_empty_uid_raises_auth_error() -> None:
    """
    VETOR DE AMEAÇA: CWE-20 (Improper Input Validation) & CWE-287.
    Tentativa de revogação de tokens fornecendo identificador vazio ou composto apenas por espaços,
    podendo acarretar falhas silenciosas ou comportamento indefinido no IdP.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    O método DEVE rejeitar fail-closed qualquer UID nulo ou em branco lançando 'AuthError'.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Um refactor pode omitir o 'strip()' ou checagem de falsy antes de enviar ao SDK externo,
    causando erros não tipados de runtime.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    UIDs vazios ou espaços lançam incondicionalmente 'AuthError' com mensagem de identificador inválido.
    """
    adapter = FirebaseAuthAdapter()

    with pytest.raises(AuthError, match="Identificador do usuário inválido"):
        await adapter.revoke_user_tokens("")

    with pytest.raises(AuthError, match="Identificador do usuário inválido"):
        await adapter.revoke_user_tokens("   ")


@pytest.mark.asyncio
async def test_user_service_delete_user_account_flow() -> None:
    """
    VETOR DE AMEAÇA: LGPD Art. 18, VI / CWE-212 (Improper Removal of Sensitive Information).
    Falha na orquestração atômica de eliminação de dados pessoais e entidades dependentes durante o encerramento da conta.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    O UserService DEVE orquestrar em transação a deleção de habilidades customizadas, exclusão
    da entidade User no banco de dados e a revogação fail-closed de tokens no provedor de autenticação.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Um desenvolvedor ou IA pode deixar de executar o commit transacional ou silenciar a revogação
    de credenciais na nuvem, violando a integridade legal da LGPD.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    O fluxo invoca rigorosamente mock_db.delete, mock_db.commit e mock_auth_port.revoke_user_tokens.
    """
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
