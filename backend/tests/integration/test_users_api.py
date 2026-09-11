"""Testes de integração dedicados para os endpoints de gestão de perfil e configurações (/users/me).

Valida consulta de preferências, criação sob demanda de UserSettings,
cifragem e limpeza de chave do Google Gemini (BYOK), e atualização de preferências parciais.
"""

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import crypto_service
from app.domain.models import User, UserSettings
from app.ports.auth_port import AuthUser

USER_SETTINGS_AUTH = AuthUser(
    uid="firebase_settings_dedicated_user",
    email="settings_dedicated@thothcvs.ai",
    full_name="Settings Dedicated User",
)


@pytest.fixture
async def setup_settings_user(async_client: AsyncClient, db_session: AsyncSession) -> dict:
    """Configura o usuário no banco de dados através da sincronização."""
    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_SETTINGS_AUTH):
        res = await async_client.post(
            "/api/v1/auth/sync",
            headers={"Authorization": "Bearer token_settings_dedicated"},
            json={"target_title": "Full Stack Architect"},
        )
        assert res.status_code == 200
        user_id = uuid.UUID(res.json()["id"])

    return {
        "user_id": user_id,
        "headers": {"Authorization": "Bearer token_settings_dedicated"},
    }


@pytest.mark.asyncio
async def test_get_and_update_settings_full_cycle(
    async_client: AsyncClient,
    setup_settings_user: dict,
    db_session: AsyncSession,
) -> None:
    """Valida consulta de configurações padrão e atualização com chave Gemini."""
    headers = setup_settings_user["headers"]
    user_id = setup_settings_user["user_id"]

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_SETTINGS_AUTH):
        # 1. GET inicial: has_gemini_key deve ser False
        get_res = await async_client.get("/api/v1/users/me/settings", headers=headers)
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["preferred_language"] == "pt-BR"
        assert data["has_gemini_key"] is False
        assert data["email_notifications_enabled"] is True
        assert data["in_app_notifications_enabled"] is True

        # 2. PUT: Cadastra chave do Gemini e altera idioma
        raw_key = "AIzaSySecretGeminiKeyForUsersMeTest123"
        put_res = await async_client.put(
            "/api/v1/users/me/settings",
            headers=headers,
            json={
                "gemini_api_key": raw_key,
                "preferred_language": "en-US",
                "email_notifications_enabled": False,
            },
        )
        assert put_res.status_code == 200
        updated = put_res.json()
        assert updated["has_gemini_key"] is True
        assert updated["preferred_language"] == "en-US"
        assert updated["email_notifications_enabled"] is False

        # 3. Confirma no banco relacional que a chave foi cifrada com AAD
        db_user = (await db_session.execute(select(User).where(User.id == user_id))).scalar_one()
        assert db_user.settings is not None
        encrypted_in_db = db_user.settings.encrypted_gemini_api_key
        assert encrypted_in_db is not None
        assert encrypted_in_db != raw_key

        # Decifra usando os dados associados do tenant (user_id)
        decrypted = crypto_service.decrypt(encrypted_in_db, associated_data=str(user_id).encode("utf-8"))
        assert decrypted == raw_key

        # 4. PUT com string vazia deve limpar a chave (remover BYOK)
        clear_res = await async_client.put(
            "/api/v1/users/me/settings",
            headers=headers,
            json={"gemini_api_key": ""},
        )
        assert clear_res.status_code == 200
        assert clear_res.json()["has_gemini_key"] is False

        # Confirma remoção no banco
        await db_session.refresh(db_user.settings)
        assert db_user.settings.encrypted_gemini_api_key is None


@pytest.mark.asyncio
async def test_update_settings_without_existing_record(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Garante que um usuário sem UserSettings existente seja criado sob demanda no PUT."""
    raw_user = User(
        id=uuid.uuid4(),
        firebase_uid="user_without_settings_uid",
        email="nosettings@thothcvs.ai",
        full_name="No Settings User",
    )
    db_session.add(raw_user)
    await db_session.commit()

    auth_mock = AuthUser(
        uid="user_without_settings_uid",
        email="nosettings@thothcvs.ai",
        full_name="No Settings User",
    )

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=auth_mock):
        headers = {"Authorization": "Bearer token_nosettings"}

        # GET cria resposta com defaults seguros
        get_res = await async_client.get("/api/v1/users/me/settings", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["has_gemini_key"] is False

        # PUT cria o registro de UserSettings sob demanda
        put_res = await async_client.put(
            "/api/v1/users/me/settings",
            headers=headers,
            json={"preferred_language": "es-ES", "in_app_notifications_enabled": False},
        )
        assert put_res.status_code == 200
        assert put_res.json()["preferred_language"] == "es-ES"
        assert put_res.json()["in_app_notifications_enabled"] is False
