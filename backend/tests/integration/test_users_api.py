"""Testes de integração dedicados para os endpoints de gestão de perfil e configurações (/users/me).

Valida consulta de preferências, criação sob demanda de UserSettings,
cifragem e limpeza de chave do Google Gemini (BYOK), e atualização de preferências parciais.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import crypto_service
from app.domain.models import (
    Application,
    CoverLetter,
    Experience,
    GeneratedResume,
    Notification,
    PromptSkill,
    User,
    UserSettings,
)
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
        decrypted = crypto_service.decrypt(
            encrypted_in_db, associated_data=str(user_id).encode("utf-8")
        )
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

        # Atualiza default_prompt_skill_id
        skill_id = uuid.uuid4()
        skill_res = await async_client.put(
            "/api/v1/users/me/settings",
            headers=headers,
            json={"default_prompt_skill_id": str(skill_id)},
        )
        assert skill_res.status_code == 200
        assert skill_res.json()["default_prompt_skill_id"] == str(skill_id)


@pytest.mark.asyncio
async def test_delete_account_lgpd_cascade_and_token_revocation(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Valida a exclusão definitiva da conta com cascata e revogação de credenciais (LGPD Art. 18).

    VETOR DE AMEAÇA:
    - LGPD Art. 18, VI / Retenção Indevida de Dados e Sessões Zumbis: Falha em eliminar
      dados pessoais do titular após solicitação expressa de exclusão de conta, ou manutenção
      de sessões/tokens válidos no provedor de identidade permitindo reentrada indevida.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O endpoint DELETE /api/v1/users/me DEVE responder HTTP 204 No Content.
    - Todos os registros vinculados ao usuário (UserSettings, experiências, candidaturas,
      documentos sintetizados, notificações e PromptSkills customizadas) DEVEM ser
      eliminados atomicamente em cascata do banco de dados.
    - PromptSkills globais do sistema (is_system_default=True) NUNCA devem ser deletadas.
    - O método revoke_user_tokens da porta de autenticação DEVE ser invocado com o UID exato
      do usuário para invalidar sessões ativas no Firebase Auth.
    - Qualquer requisição subsequente com as credenciais do usuário excluído DEVE falhar com 404.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Nunca substitua a eliminação atômica por soft delete (deleted_at) neste endpoint sem
      garantir a expurgação física dos dados pessoais exigida pelo Art. 18 da LGPD.
    - Nunca remova a chamada ao auth_port.revoke_user_tokens para 'simplificar' o endpoint,
      pois deixaria tokens JWT ativos no cliente permitindo contornar a exclusão.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Confirmação direta no banco relacional de que select(User).where(User.id == user.id)
      retorna None, de que entidades filhas foram removidas em cascata, e de que
      revoke_user_tokens foi invocado com o firebase_uid real.
    """
    user = User(
        id=uuid.uuid4(),
        firebase_uid="firebase_lgpd_victim_uid",
        email="lgpd_victim@thothcvs.ai",
        full_name="LGPD Victim User",
    )
    db_session.add(user)
    await db_session.flush()

    settings = UserSettings(user_id=user.id, preferred_language="pt-BR")
    experience = Experience(
        user_id=user.id,
        company_name="LGPD Inc",
        position_title="Privacy Officer",
        work_model="remote",
        start_date=date(2022, 1, 1),
        description="Gestão de conformidade LGPD e privacidade de dados.",
    )
    application = Application(
        user_id=user.id,
        company_name="Compliance Corp",
        job_title="DPO",
        job_description="LGPD compliance",
    )
    db_session.add_all([settings, experience, application])
    await db_session.flush()

    custom_skill = PromptSkill(
        slug=f"custom-user-skill-lgpd-{uuid.uuid4().hex[:8]}",
        name="Custom Skill",
        description="Custom skill for user",
        system_prompt="Custom prompt",
        is_system_default=False,
        created_by_user_id=user.id,
    )
    system_skill = PromptSkill(
        slug=f"system-default-skill-lgpd-{uuid.uuid4().hex[:8]}",
        name="System Skill",
        description="System default skill",
        system_prompt="Default prompt",
        is_system_default=True,
    )
    db_session.add_all([custom_skill, system_skill])
    await db_session.flush()

    resume = GeneratedResume(
        application_id=application.id,
        user_id=user.id,
        prompt_skill_id=custom_skill.id,
        structured_content={"title": "Resume"},
    )
    cover_letter = CoverLetter(
        application_id=application.id,
        user_id=user.id,
        content="Cover letter text",
    )
    notification = Notification(
        user_id=user.id,
        application_id=application.id,
        notification_type="general",
        title="Welcome",
        message="Welcome to the platform",
    )
    db_session.add_all([resume, cover_letter, notification])
    await db_session.commit()

    auth_mock = AuthUser(
        uid="firebase_lgpd_victim_uid",
        email="lgpd_victim@thothcvs.ai",
        full_name="LGPD Victim User",
    )

    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", return_value=auth_mock),
        patch(
            "app.api.v1.deps.auth_adapter.revoke_user_tokens", new_callable=AsyncMock
        ) as mock_revoke,
    ):
        headers = {"Authorization": "Bearer token_lgpd_victim"}
        del_res = await async_client.delete("/api/v1/users/me", headers=headers)
        assert del_res.status_code == 204

        # Oráculo 1: Usuário não existe mais no banco
        user_check = await db_session.execute(select(User).where(User.id == user.id))
        assert user_check.scalar_one_or_none() is None

        # Oráculo 2: Entidades filhas foram limpas em cascata
        settings_check = await db_session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        assert settings_check.scalar_one_or_none() is None

        exp_check = await db_session.execute(
            select(Experience).where(Experience.user_id == user.id)
        )
        assert exp_check.scalar_one_or_none() is None

        app_check = await db_session.execute(
            select(Application).where(Application.user_id == user.id)
        )
        assert app_check.scalar_one_or_none() is None

        res_check = await db_session.execute(
            select(GeneratedResume).where(GeneratedResume.user_id == user.id)
        )
        assert res_check.scalar_one_or_none() is None

        cl_check = await db_session.execute(
            select(CoverLetter).where(CoverLetter.user_id == user.id)
        )
        assert cl_check.scalar_one_or_none() is None

        notif_check = await db_session.execute(
            select(Notification).where(Notification.user_id == user.id)
        )
        assert notif_check.scalar_one_or_none() is None

        # Oráculo 3: PromptSkill customizada deletada, mas system default preservada
        custom_skill_check = await db_session.execute(
            select(PromptSkill).where(PromptSkill.id == custom_skill.id)
        )
        assert custom_skill_check.scalar_one_or_none() is None

        system_skill_check = await db_session.execute(
            select(PromptSkill).where(PromptSkill.id == system_skill.id)
        )
        assert system_skill_check.scalar_one_or_none() is not None

        # Oráculo 4: Revogação de tokens chamada com o UID do Firebase
        mock_revoke.assert_called_once_with("firebase_lgpd_victim_uid")

        # Oráculo 5: Requisição subsequente retorna 404
        get_res = await async_client.get("/api/v1/users/me/settings", headers=headers)
        assert get_res.status_code == 404
