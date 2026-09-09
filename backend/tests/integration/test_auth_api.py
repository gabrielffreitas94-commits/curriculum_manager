"""Testes de integração para os endpoints de autenticação e configurações de usuário."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import User
from app.ports.auth_port import AuthUser


@pytest.mark.asyncio
async def test_auth_sync_creates_new_user(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Testa a sincronização inicial de um novo usuário autenticado via Firebase."""
    mock_auth_user = AuthUser(
        uid="firebase_sync_uid_1",
        email="newuser@thothcvs.ai",
        full_name="New Thoth User",
        picture_url=None,
    )

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=mock_auth_user):
        response = await async_client.post(
            "/api/v1/auth/sync",
            headers={"Authorization": "Bearer mock_token_abc"},
            json={"target_title": "Full Stack Engineer"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newuser@thothcvs.ai"
        assert data["full_name"] == "New Thoth User"
        assert data["firebase_uid"] == "firebase_sync_uid_1"
        assert data["target_title"] == "Full Stack Engineer"
        assert data["settings"] is not None
        assert data["settings"]["preferred_language"] == "pt-BR"


@pytest.mark.asyncio
async def test_auth_sync_idempotent_returns_existing_user(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Garante que chamadas subsequentes a /sync retornem o usuário existente sem duplicação."""
    mock_auth_user = AuthUser(
        uid="firebase_sync_uid_existing",
        email="existing@thothcvs.ai",
        full_name="Existing User",
    )

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=mock_auth_user):
        # Primeira chamada
        res1 = await async_client.post(
            "/api/v1/auth/sync",
            headers={"Authorization": "Bearer mock_token_existing"},
        )
        assert res1.status_code == 200
        user_id_1 = res1.json()["id"]

        # Segunda chamada com mesmo token
        res2 = await async_client.post(
            "/api/v1/auth/sync",
            headers={"Authorization": "Bearer mock_token_existing"},
        )
        assert res2.status_code == 200
        user_id_2 = res2.json()["id"]

        assert user_id_1 == user_id_2


@pytest.mark.asyncio
async def test_auth_sync_missing_token_unauthorized(
    async_client: AsyncClient,
) -> None:
    """Testa rejeição com 401 caso o cabeçalho Authorization não seja informado."""
    response = await async_client.post("/api/v1/auth/sync")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_settings_get_and_update_with_crypto(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Testa consulta e atualização das configurações e cifragem da chave Gemini."""
    mock_auth_user = AuthUser(
        uid="firebase_settings_uid",
        email="settings_user@thothcvs.ai",
        full_name="Settings Tester",
    )

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=mock_auth_user):
        # Sincroniza o usuário primeiro
        sync_res = await async_client.post(
            "/api/v1/auth/sync",
            headers={"Authorization": "Bearer mock_token_settings"},
        )
        assert sync_res.status_code == 200

        # Obtém configurações atuais
        get_res = await async_client.get(
            "/api/v1/users/me/settings",
            headers={"Authorization": "Bearer mock_token_settings"},
        )
        assert get_res.status_code == 200
        settings_data = get_res.json()
        assert settings_data["has_gemini_key"] is False

        # Atualiza salvando a API key do Gemini
        raw_api_key = "AIzaSySecretTestingApiKey123"
        put_res = await async_client.put(
            "/api/v1/users/me/settings",
            headers={"Authorization": "Bearer mock_token_settings"},
            json={
                "gemini_api_key": raw_api_key,
                "preferred_language": "en-US",
                "email_notifications_enabled": False,
            },
        )
        assert put_res.status_code == 200
        updated = put_res.json()
        assert updated["has_gemini_key"] is True
        assert updated["preferred_language"] == "en-US"
        assert updated["email_notifications_enabled"] is False

        # Verifica no banco que a chave está cifrada (não em texto plano)
        import uuid
        user_id = uuid.UUID(sync_res.json()["id"])
        from sqlalchemy import select
        db_user = (await db_session.execute(select(User).where(User.id == user_id))).scalar_one()
        assert db_user.settings.encrypted_gemini_api_key is not None
        assert db_user.settings.encrypted_gemini_api_key != raw_api_key
