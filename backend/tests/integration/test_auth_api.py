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


@pytest.mark.asyncio
async def test_auth_sync_real_rs256_token_integration(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Valida o fluxo ponta a ponta de autenticação HTTP com JWT assinado via RS256."""
    import time

    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from app.api.v1 import deps

    # Gera par RSA legítimo
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    payload = {
        "sub": "rs256_real_uid_101",
        "email": "real_rsa@thothcvs.ai",
        "name": "RSA Verified User",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    valid_token = jwt.encode(payload, pem_private, algorithm="RS256")

    # Injeta a chave pública legítima no adaptador global
    original_pk = deps.auth_adapter._public_key
    deps.auth_adapter._public_key = pem_public
    try:
        response = await async_client.post(
            "/api/v1/auth/sync",
            headers={"Authorization": f"Bearer {valid_token}"},
            json={"target_title": "Security Engineer"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["firebase_uid"] == "rs256_real_uid_101"
        assert data["email"] == "real_rsa@thothcvs.ai"
        assert data["full_name"] == "RSA Verified User"
    finally:
        deps.auth_adapter._public_key = original_pk


@pytest.mark.asyncio
async def test_auth_sync_forged_rs256_token_returns_401(
    async_client: AsyncClient,
) -> None:
    """Garante que requisições HTTP com JWT forjado recebam HTTP 401 Unauthorized.

    VETOR DE AMEAÇA:
    - OWASP A07:2021 (Broken Authentication) / CWE-287.
    - Impacto: Acesso indevido a endpoints da API através de tokens forjados externamente.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - A API DEVE interceptar o token com assinatura inválida e retornar status HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Se o middleware ou dependência get_current_user ignorar erros de assinatura ou engolir
      exceções retornando usuário anônimo ou padrão, a rota seria indevidamente acessível.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Envia requisição HTTP real com JWT assinado por chave invasora e assere status_code == 401.
    """
    import time

    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from app.api.v1 import deps

    # Chave do servidor legítimo
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_public_server = server_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Chave do invasor
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_private_attacker = attacker_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    payload = {
        "sub": "victim_uid_999",
        "email": "victim@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    forged_token = jwt.encode(payload, pem_private_attacker, algorithm="RS256")

    original_pk = deps.auth_adapter._public_key
    deps.auth_adapter._public_key = pem_public_server
    try:
        response = await async_client.post(
            "/api/v1/auth/sync",
            headers={"Authorization": f"Bearer {forged_token}"},
        )
        assert response.status_code == 401
        assert "inválida ou expirada" in response.json()["detail"]
    finally:
        deps.auth_adapter._public_key = original_pk
