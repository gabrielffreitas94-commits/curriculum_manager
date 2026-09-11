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
