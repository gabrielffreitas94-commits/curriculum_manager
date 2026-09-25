"""Testes de integração para os fluxos da Sprint 4: Configurações, BYOK Gemini, i18n & LGPD.

Valida a proteção criptográfica AES-GCM-256 com Dados Associados (AAD) da chave pessoal do Gemini,
preferências de idioma e dialeto regional, exportação de dados (Art. 18 LGPD)
e eliminação definitiva de contas com barreira fail-closed de autenticação.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.core.crypto import crypto_service
from app.domain.models import User, UserSettings

MOCK_USER_ID = uuid.uuid4()
MOCK_WEB_USER = User(
    id=MOCK_USER_ID,
    firebase_uid="firebase_sprint4_tester_uid",
    email="sprint4_tester@thothcvs.ai",
    full_name="Carla Security Architect",
    target_title="Principal Security Engineer",
    phone="+55 11 97777-6666",
    location="Belo Horizonte, MG",
    linkedin_url="https://linkedin.com/in/carlasec",
    github_url="https://github.com/carlasec",
    professional_summary="Especialista em segurança de aplicações e criptografia aplicada.",
)

MOCK_USER_SETTINGS = UserSettings(
    id=uuid.uuid4(),
    user_id=MOCK_USER_ID,
    encrypted_gemini_api_key=crypto_service.encrypt(
        "AIzaSyTestApiKeyMock123456789",
        associated_data=str(MOCK_USER_ID).encode("utf-8"),
    ),
    preferred_language="pt-BR",
    email_notifications_enabled=True,
    in_app_notifications_enabled=True,
)


# ==============================================================================
# GUARDRAILS ANTI-REGRESSÃO: AUTENTICAÇÃO FAIL-CLOSED (SPRINT 4)
# ==============================================================================


@pytest.mark.asyncio
async def test_guardrail_settings_unauthenticated_redirects(async_client: AsyncClient) -> None:
    """Valida proteção fail-closed da central de configurações para usuários anônimos.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Visualização indevida de dados de conta e configuração de IA.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Requisições anônimas a GET /settings DEVEM ser redirecionadas para '/?auth_error=login_required' com status 302.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Permitir acesso anônimo causaria exceções de contexto e falhas de autorização.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - GET /settings sem sessão DEVE responder com HTTP 302 para login.
    """
    res = await async_client.get("/settings", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=login_required"


@pytest.mark.asyncio
async def test_guardrail_settings_gemini_key_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed que bloqueia salvamento de chaves sem sessão ativa.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Submissão de chaves de API sem vínculo de propriedade com usuário.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - POST /settings/gemini-key sem sessão DEVE responder com HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Qualquer tentativa de flexibilizar o endpoint compromete o modelo multi-tenant.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /settings/gemini-key sem sessão DEVE retornar HTTP 401.
    """
    res = await async_client.post(
        "/settings/gemini-key",
        data={"gemini_api_key": "AIzaSyTest"},
    )
    assert res.status_code == 401
    assert "login_required" in res.text


@pytest.mark.asyncio
async def test_guardrail_settings_test_gemini_key_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida proteção fail-closed para teste de conectividade com a API do Gemini.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Utilização do backend como proxy anônimo para testar chaves de terceiros.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - POST /settings/gemini-key/test sem sessão DEVE ser imediatamente rejeitado com HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Permitir testes anônimos tornaria o servidor vulnerável a ataques de oráculo de validação.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /settings/gemini-key/test sem sessão DEVE retornar HTTP 401.
    """
    res = await async_client.post("/settings/gemini-key/test", data={})
    assert res.status_code == 401
    assert "login_required" in res.text


@pytest.mark.asyncio
async def test_guardrail_settings_remove_gemini_key_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida proteção fail-closed para remoção de chave pessoal de IA.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Desativação maliciosa de cotas BYOK de outros usuários.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - POST /settings/gemini-key/remove sem sessão DEVE retornar HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Remover chaves sem autenticação abriria brecha de negação de serviço.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /settings/gemini-key/remove sem sessão DEVE responder com HTTP 401.
    """
    res = await async_client.post("/settings/gemini-key/remove")
    assert res.status_code == 401
    assert "login_required" in res.text


@pytest.mark.asyncio
async def test_guardrail_settings_language_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed para alteração de idioma persistido do usuário.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Alteração indevida de preferências de conta.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - POST /settings/language sem sessão DEVE retornar HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Salvar preferências sem contexto de usuário causaria erros de integridade relacional.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /settings/language sem sessão DEVE retornar HTTP 401.
    """
    res = await async_client.post(
        "/settings/language",
        data={"preferred_language": "en-US"},
    )
    assert res.status_code == 401
    assert "login_required" in res.text


@pytest.mark.asyncio
async def test_guardrail_settings_export_data_unauthenticated_redirects(
    async_client: AsyncClient,
) -> None:
    """Valida que a exportação de dados pessoais (LGPD Art. 18) exige sessão válida.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function / CWE-200: Information Exposure.
    - Impacto Potencial: Vazamento massivo de todo o histórico do candidato.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - GET /settings/export-data sem sessão DEVE responder com HTTP 302 redirecionando para login.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Permitir download anônimo violaria frontalmente a LGPD e privacidade do usuário.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - GET /settings/export-data sem sessão DEVE retornar HTTP 302.
    """
    res = await async_client.get("/settings/export-data", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=login_required"


@pytest.mark.asyncio
async def test_guardrail_settings_delete_account_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed para exclusão definitiva de conta (LGPD Art. 18, VI).

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function / CSRF.
    - Impacto Potencial: Destruição irreversível de contas sem autenticação.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - POST /settings/delete-account sem sessão DEVE responder com HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Permitir invocação desprotegida causaria perda catastrófica e acidental de dados.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /settings/delete-account sem sessão DEVE retornar HTTP 401.
    """
    res = await async_client.post("/settings/delete-account")
    assert res.status_code == 401
    assert "login_required" in res.text


# ==============================================================================
# FLUXOS AUTENTICADOS: BYOK GEMINI, I18N E LGPD
# ==============================================================================


@pytest.mark.asyncio
async def test_settings_page_renders_with_existing_settings(async_client: AsyncClient) -> None:
    """Valida renderização completa da página de configurações com chave BYOK ativa."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = MOCK_USER_SETTINGS

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_settings,
        ),
    ):
        res = await async_client.get("/settings")
        assert res.status_code == 200
        content = res.text
        assert "Configurações da Conta & IA" in content
        assert "Google Gemini API (Bring Your Own Key)" in content
        assert "Chave Pessoal Ativa (AES-GCM-256)" in content
        assert "Preferências de Idioma & Síntese Regional" in content
        assert "Privacidade & Direitos do Titular (LGPD Art. 18)" in content
        assert "Remover chave pessoal" in content


@pytest.mark.asyncio
async def test_settings_page_renders_without_existing_settings(async_client: AsyncClient) -> None:
    """Valida renderização com cota padrão compartilhada quando não há chave cadastrada."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = None

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_settings,
        ),
    ):
        res = await async_client.get("/settings")
        assert res.status_code == 200
        content = res.text
        assert "Cota Padrão Compartilhada" in content


@pytest.mark.asyncio
async def test_settings_save_gemini_key_success(async_client: AsyncClient) -> None:
    """Valida encriptação autenticada com AAD e persistência da chave de API."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = MOCK_USER_SETTINGS

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_settings,
        ),
        patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock) as mock_commit,
    ):
        res = await async_client.post(
            "/settings/gemini-key",
            data={"gemini_api_key": "AIzaSyNewTestKey987654"},
        )
        assert res.status_code == 200
        assert "Chave do Google Gemini salva e cifrada com sucesso" in res.text
        mock_commit.assert_awaited_once()

        # Valida que a chave foi cifrada com AES-GCM-256 e decifrável apenas com o AAD do usuário
        user_aad = str(MOCK_USER_ID).encode("utf-8")
        decrypted = crypto_service.decrypt(
            MOCK_USER_SETTINGS.encrypted_gemini_api_key,
            associated_data=user_aad,
        )
        assert decrypted == "AIzaSyNewTestKey987654"


@pytest.mark.asyncio
async def test_settings_save_gemini_key_creates_new_settings_if_none(
    async_client: AsyncClient,
) -> None:
    """Valida instanciação e persistência de novo UserSettings quando inexistente."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = None

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_settings,
        ),
        patch("sqlalchemy.ext.asyncio.AsyncSession.add") as mock_add,
        patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock) as mock_commit,
    ):
        res = await async_client.post(
            "/settings/gemini-key",
            data={"gemini_api_key": "AIzaSyFreshKey123"},
        )
        assert res.status_code == 200
        assert "Chave do Google Gemini salva e cifrada com sucesso" in res.text
        mock_add.assert_called_once()
        mock_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_settings_save_gemini_key_empty_rejected(async_client: AsyncClient) -> None:
    """Valida rejeição com HTTP 400 de chave em branco."""
    async_client.cookies.set("session_token", "valid_session_token")

    with patch(
        "app.services.auth_service.AuthService.get_authenticated_user",
        new_callable=AsyncMock,
        return_value=MOCK_WEB_USER,
    ):
        res = await async_client.post(
            "/settings/gemini-key",
            data={"gemini_api_key": "   "},
        )
        assert res.status_code == 400
        assert "A chave de API não pode estar em branco" in res.text


@pytest.mark.asyncio
async def test_settings_test_gemini_key_with_explicit_key_success(
    async_client: AsyncClient,
) -> None:
    """Valida teste de chave fornecida no formulário com resposta positiva."""
    async_client.cookies.set("session_token", "valid_session_token")

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.adapters.gemini_ai_adapter.GeminiAIAdapter.analyze_job",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ),
    ):
        res = await async_client.post(
            "/settings/gemini-key/test",
            data={"gemini_api_key": "AIzaSyExplicitTestKey"},
        )
        assert res.status_code == 200
        assert "Conexão com a Google Gemini API validada com sucesso" in res.text


@pytest.mark.asyncio
async def test_settings_test_gemini_key_with_saved_key(async_client: AsyncClient) -> None:
    """Valida teste da chave já persistida no banco decifrada com AAD."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = MOCK_USER_SETTINGS

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_settings,
        ),
        patch(
            "app.adapters.gemini_ai_adapter.GeminiAIAdapter.analyze_job",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ),
    ):
        res = await async_client.post(
            "/settings/gemini-key/test",
            data={"gemini_api_key": ""},
        )
        assert res.status_code == 200
        assert "Conexão com a Google Gemini API validada com sucesso" in res.text


@pytest.mark.asyncio
async def test_settings_test_gemini_key_failure(async_client: AsyncClient) -> None:
    """Valida tratamento e log de erro ao falhar na chamada ao Google AI Studio."""
    async_client.cookies.set("session_token", "valid_session_token")

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.adapters.gemini_ai_adapter.GeminiAIAdapter.analyze_job",
            new_callable=AsyncMock,
            side_effect=Exception("API_KEY_INVALID: The provided API key is expired."),
        ),
    ):
        res = await async_client.post(
            "/settings/gemini-key/test",
            data={"gemini_api_key": "AIzaSyBadKey"},
        )
        assert res.status_code == 200
        assert "Falha ao validar a chave com o Google AI Studio" in res.text
        assert "API_KEY_INVALID" in res.text


@pytest.mark.asyncio
async def test_settings_test_gemini_key_no_key_provided(async_client: AsyncClient) -> None:
    """Valida feedback de aviso quando nenhuma chave está cadastrada ou preenchida."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = None

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_settings,
        ),
    ):
        res = await async_client.post(
            "/settings/gemini-key/test",
            data={"gemini_api_key": ""},
        )
        assert res.status_code == 200
        assert "Nenhuma chave informada ou cadastrada para teste" in res.text


@pytest.mark.asyncio
async def test_settings_test_gemini_key_decrypt_exception(async_client: AsyncClient) -> None:
    """Valida tratamento seguro de chave cifrada corrompida."""
    async_client.cookies.set("session_token", "valid_session_token")

    corrupted_settings = UserSettings(
        id=uuid.uuid4(),
        user_id=MOCK_USER_ID,
        encrypted_gemini_api_key="corrupted_base64_ciphertext_payload",
    )

    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = corrupted_settings

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_settings,
        ),
    ):
        res = await async_client.post(
            "/settings/gemini-key/test",
            data={"gemini_api_key": ""},
        )
        assert res.status_code == 200
        assert "Nenhuma chave informada ou cadastrada para teste" in res.text


@pytest.mark.asyncio
async def test_settings_remove_gemini_key_success(async_client: AsyncClient) -> None:
    """Valida desativação da chave pessoal e restauração da cota padrão."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = MOCK_USER_SETTINGS

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_settings,
        ),
        patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock) as mock_commit,
    ):
        res = await async_client.post("/settings/gemini-key/remove")
        assert res.status_code == 200
        assert "Chave pessoal removida" in res.text
        assert MOCK_USER_SETTINGS.encrypted_gemini_api_key is None
        mock_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_settings_remove_gemini_key_when_no_settings_exists(
    async_client: AsyncClient,
) -> None:
    """Valida execução suave da remoção mesmo se UserSettings for inexistente."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = None

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_settings,
        ),
    ):
        res = await async_client.post("/settings/gemini-key/remove")
        assert res.status_code == 200
        assert "Chave pessoal removida" in res.text


@pytest.mark.asyncio
async def test_settings_update_language_success(async_client: AsyncClient) -> None:
    """Valida atualização do idioma preferido no banco e no cookie HTTP-only."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = MOCK_USER_SETTINGS

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_settings,
        ),
        patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock) as mock_commit,
    ):
        res = await async_client.post(
            "/settings/language",
            data={"preferred_language": "en-US"},
        )
        assert res.status_code == 200
        assert "en-US" in res.text
        assert res.cookies.get("locale") == "en-US"
        assert MOCK_USER_SETTINGS.preferred_language == "en-US"
        mock_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_settings_update_language_creates_new_settings_if_none(
    async_client: AsyncClient,
) -> None:
    """Valida instanciação e gravação de novo UserSettings ao atualizar idioma."""
    async_client.cookies.set("session_token", "valid_session_token")

    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = None

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_db_settings,
        ),
        patch("sqlalchemy.ext.asyncio.AsyncSession.add") as mock_add,
        patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock) as mock_commit,
    ):
        res = await async_client.post(
            "/settings/language",
            data={"preferred_language": "es-ES"},
        )
        assert res.status_code == 200
        assert "es-ES" in res.text
        assert res.cookies.get("locale") == "es-ES"
        mock_add.assert_called_once()
        mock_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_settings_export_data_json_portability(async_client: AsyncClient) -> None:
    """Valida conformidade com portabilidade de dados da LGPD (Art. 18, II e V)."""
    async_client.cookies.set("session_token", "valid_session_token")

    from types import SimpleNamespace

    mock_dossier = {
        "experiences": [
            SimpleNamespace(
                company_name="CloudSec Inc",
                position_title="Security Lead",
                start_date="2020-01",
                end_date=None,
                tech_stack=["Python", "Terraform"],
                achievements=["Zero security breaches."],
            )
        ],
        "skills": [SimpleNamespace(name="AppSec"), SimpleNamespace(name="Cryptography")],
        "educations": [
            SimpleNamespace(
                institution_name="UFMG",
                degree="Mestrado",
                field_of_study="Ciência da Computação",
                start_date="2018",
                end_date="2020",
            )
        ],
        "certifications": [
            SimpleNamespace(name="CISSP", issuing_organization="ISC2"),
        ],
    }

    mock_application = MagicMock(
        id=uuid.uuid4(),
        company_name="Google",
        job_title="Security Engineer",
        status="applied",
        applied_at="2026-03-01",
    )

    mock_resumes = MagicMock()
    mock_resumes.scalars.return_value.all.return_value = [MagicMock()]

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.profile_service.ProfileService.get_full_dossier",
            new_callable=AsyncMock,
            return_value=mock_dossier,
        ),
        patch(
            "app.services.application_service.ApplicationService.list_applications",
            new_callable=AsyncMock,
            return_value=[mock_application],
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_resumes,
        ),
    ):
        res = await async_client.get("/settings/export-data")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/json"
        assert (
            'attachment; filename="thothcvs_meus_dados.json"' in res.headers["content-disposition"]
        )

        data = json.loads(res.content)
        assert data["user_profile"]["full_name"] == "Carla Security Architect"
        assert data["user_profile"]["email"] == "sprint4_tester@thothcvs.ai"
        assert len(data["dossier"]["experiences"]) == 1
        assert data["dossier"]["experiences"][0]["company_name"] == "CloudSec Inc"
        assert "AppSec" in data["dossier"]["skills"]
        assert "CISSP" in [c["name"] for c in data["dossier"]["certifications"]]
        assert "Portabilidade" in data["compliance"]


@pytest.mark.asyncio
async def test_settings_delete_account_lgpd_erasure(async_client: AsyncClient) -> None:
    """Valida eliminação definitiva de conta e dados com revogação de cookie de sessão."""
    async_client.cookies.set("session_token", "valid_session_token")

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.user_service.UserService.delete_user_account",
            new_callable=AsyncMock,
        ) as mock_delete,
    ):
        res = await async_client.post("/settings/delete-account")
        assert res.status_code == 200
        assert res.headers.get("hx-redirect") == "/?msg=account_deleted"
        mock_delete.assert_awaited_once_with(MOCK_WEB_USER)
