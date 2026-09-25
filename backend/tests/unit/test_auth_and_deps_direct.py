"""Testes unitários diretos para os endpoints de autenticação e dependências (auth.py e deps.py).

Garante cobertura completa de 100% cobrindo criação inicial de usuário, atualização
de usuário existente, erros 401 (InvalidTokenError, AuthError), 404 de usuário não
sincronizado e injeção de dependências.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.v1.auth import sync_user
from app.api.v1.deps import get_current_auth_user, get_current_user, get_document_service
from app.api.v1.schemas.user import UserSyncRequest
from app.domain.models import User, UserSettings
from app.ports.auth_port import AuthError, AuthUser, InvalidTokenError


@pytest.mark.asyncio
async def test_sync_user_new_user_direct() -> None:
    """Testa sincronização quando o usuário não existe no banco (criação)."""
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    def mock_add(entity: object) -> None:
        if getattr(entity, "id", None) is None:
            entity.id = uuid.uuid4()

    db.add.side_effect = mock_add
    db.flush = AsyncMock()

    auth_user = AuthUser(
        uid="new_uid_123",
        email="new@test.com",
        full_name="New User",
    )
    payload = UserSyncRequest(target_title="Senior Engineer", phone="1199999", location="SP")

    res = await sync_user(body=payload, auth_user=auth_user, db=db)
    assert res.email == "new@test.com"
    assert res.firebase_uid == "new_uid_123"
    assert res.settings.has_gemini_key is False


@pytest.mark.asyncio
async def test_sync_user_existing_user_with_and_without_settings() -> None:
    """Testa sincronização quando o usuário já existe no banco."""
    # 1. Usuário existente sem settings
    existing_user_no_settings = User(
        id=uuid.uuid4(),
        firebase_uid="exist_uid_1",
        email="exist@test.com",
        full_name="Old Name",
        is_active=True,
    )
    existing_user_no_settings.settings = None

    db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_user_no_settings
    db.execute = AsyncMock(return_value=mock_result)
    db.add.side_effect = lambda e: None

    db.flush = AsyncMock()

    auth_user = AuthUser(
        uid="exist_uid_1",
        email="exist@test.com",
        full_name="Updated Name",
    )
    payload = UserSyncRequest(target_title="Lead Architect", phone="123", location="RJ")

    res1 = await sync_user(body=payload, auth_user=auth_user, db=db)
    assert res1.full_name == "Updated Name"
    assert res1.target_title == "Lead Architect"
    assert res1.settings.has_gemini_key is False

    # 2. Usuário existente com chave Gemini salva
    settings = UserSettings(
        user_id=existing_user_no_settings.id,
        encrypted_gemini_api_key="encrypted_key_sample",
        preferred_language="pt-BR",
        email_notifications_enabled=True,
        in_app_notifications_enabled=True,
    )

    existing_user_with_settings = User(
        id=uuid.uuid4(),
        firebase_uid="exist_uid_2",
        email="exist2@test.com",
        full_name="Key User",
        is_active=True,
    )

    existing_user_with_settings.settings = settings

    mock_result2 = MagicMock()
    mock_result2.scalar_one_or_none.return_value = existing_user_with_settings
    db.execute = AsyncMock(return_value=mock_result2)

    res2 = await sync_user(body=None, auth_user=auth_user, db=db)
    assert res2.settings.has_gemini_key is True


@pytest.mark.asyncio
async def test_deps_auth_exceptions_and_current_user() -> None:
    """Valida exceções de autenticação e busca de usuário em deps.py."""
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad_token")

    # 1. InvalidTokenError -> 401
    with pytest.MonkeyPatch.context() as mp:
        mock_adapter = MagicMock()
        mock_adapter.verify_token = AsyncMock(side_effect=InvalidTokenError("Token expirado"))
        mp.setattr("app.api.v1.deps.auth_adapter", mock_adapter)

        with pytest.raises(HTTPException) as exc_inv:
            await get_current_auth_user(credentials=creds)
        assert exc_inv.value.status_code == 401
        assert "inválida ou expirada" in exc_inv.value.detail

    # 2. AuthError -> 401
    with pytest.MonkeyPatch.context() as mp:
        mock_adapter = MagicMock()
        mock_adapter.verify_token = AsyncMock(side_effect=AuthError("Falha geral"))
        mp.setattr("app.api.v1.deps.auth_adapter", mock_adapter)

        with pytest.raises(HTTPException) as exc_auth:
            await get_current_auth_user(credentials=creds)
        assert exc_auth.value.status_code == 401
        assert "Falha de autenticação" in exc_auth.value.detail

    # 3. get_current_user -> 404 se user for None
    db = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_res)

    auth_u = AuthUser(uid="missing_uid", email="a@b.com", full_name="A")
    with pytest.raises(HTTPException) as exc_404:
        await get_current_user(auth_user=auth_u, db=db)
    assert exc_404.value.status_code == 404

    # 4. get_current_user -> sucesso
    user_mock = User(id=uuid.uuid4(), firebase_uid="ok_uid", email="ok@b.com")
    mock_res.scalar_one_or_none.return_value = user_mock
    res_user = await get_current_user(auth_user=auth_u, db=db)
    assert res_user == user_mock

    # 5. get_document_service factory
    doc_service = await get_document_service(db=db)
    assert doc_service is not None


def test_guardrail_resolve_gemini_api_key_security(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida resolução e decifração de chave Gemini com AAD de segurança e fallbacks.

    VETOR DE AMEAÇA:
    - CWE-312: Cleartext Storage of Sensitive Information.
    - CWE-327: Use of a Broken or Risky Cryptographic Algorithm.
    - Impacto Potencial: Vazamento de chaves BYOK de usuários ou descriptografia cruzada
      indevida entre tenants.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O sistema DEVE decifrar a chave privada do usuário usando seu user_id como
      Associated Authenticated Data (AAD).
    - Caso a decifração com AAD falhe, tenta compatibilidade sem AAD.
    - Se ambas falharem ou o usuário não tiver chave própria, DEVE recorrer de forma segura
      à variável de ambiente GEMINI_API_KEY.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Descartar a validação de AAD ou armazenar a chave em texto puro compromete a segurança
      de segredos por usuário.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Assere que chave criptografada com AAD retorna o plaintext correto, chave legada
      descriptografa no fallback, e falha total recorre à variável de ambiente sem quebrar.
    """
    from app.api.v1.deps import (
        resolve_gemini_api_key,
    )
    from app.core.crypto import crypto_service

    monkeypatch.setenv("GEMINI_API_KEY", "env_gemini_fallback_key")

    # 1. Usuário None -> Recorre ao ambiente
    assert resolve_gemini_api_key(None) == "env_gemini_fallback_key"

    # 2. Usuário sem settings -> Recorre ao ambiente
    user_no_settings = User(id=uuid.uuid4(), email="no_settings@thoth.ai")
    assert resolve_gemini_api_key(user_no_settings) == "env_gemini_fallback_key"

    # 3. Usuário com chave cifrada com AAD (padrão seguro)
    user_id = uuid.uuid4()
    aad = str(user_id).encode("utf-8")
    enc_key_with_aad = crypto_service.encrypt("secret_byok_with_aad", associated_data=aad)
    user_with_aad = User(id=user_id, email="aad@thoth.ai")
    user_with_aad.settings = UserSettings(encrypted_gemini_api_key=enc_key_with_aad)
    assert resolve_gemini_api_key(user_with_aad) == "secret_byok_with_aad"

    # 4. Usuário com chave legada sem AAD (fallback 1)
    enc_key_legacy = crypto_service.encrypt("secret_legacy_no_aad")
    user_legacy = User(id=uuid.uuid4(), email="legacy@thoth.ai")
    user_legacy.settings = UserSettings(encrypted_gemini_api_key=enc_key_legacy)
    assert resolve_gemini_api_key(user_legacy) == "secret_legacy_no_aad"

    # 5. Chave corrompida que falha em ambos os decrypts -> fallback para env
    user_corrupt = User(id=uuid.uuid4(), email="corrupt@thoth.ai")
    user_corrupt.settings = UserSettings(
        encrypted_gemini_api_key="corrupted_ciphertext_not_valid_b64"
    )
    assert resolve_gemini_api_key(user_corrupt) == "env_gemini_fallback_key"


@pytest.mark.asyncio
async def test_get_resume_parser_adapter_and_profile_service() -> None:
    """Valida instanciação das fábricas de parsing de currículo e serviço de perfil."""
    from app.adapters.gemini_resume_parser_adapter import GeminiResumeParserAdapter
    from app.api.v1.deps import get_profile_service, get_resume_parser_adapter
    from app.services.profile_service import ProfileService

    adapter = get_resume_parser_adapter(api_key="mock_key_123")
    assert isinstance(adapter, GeminiResumeParserAdapter)
    assert adapter._api_key == "mock_key_123"

    mock_db = MagicMock()
    prof_service = await get_profile_service(db=mock_db)
    assert isinstance(prof_service, ProfileService)
    assert prof_service._db == mock_db
