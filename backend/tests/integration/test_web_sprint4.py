"""Testes de integração para os fluxos da Sprint 4: Configurações, BYOK Gemini, i18n & LGPD.

Valida a proteção criptográfica AES-GCM-256 com Dados Associados (AAD) da chave pessoal do Gemini,
preferências de idioma e dialeto regional, exportação de dados (Art. 18 LGPD)
e eliminação definitiva de contas com barreira fail-closed de autenticação.
"""

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from httpx import AsyncClient

from app.api.web import _extract_updated_resume_content, google_callback
from app.core.crypto import crypto_service
from app.domain.models import (
    Application,
    GeneratedResume,
    PromptSkill,
    User,
    UserSettings,
)
from app.ports.ai_port import ModelUnavailableError
from app.services.auth_service import AuthService

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
        assert "API_KEY_INVALID" not in res.text


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
    """
    VETOR DE AMEAÇA: LGPD Art. 18, II e V / CWE-200 (Information Exposure).
    Violação de direitos do titular de dados ou vazamento cruzado de dados de terceiros
    durante a geração e download do arquivo de portabilidade de dados pessoais.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    A rota DEVE gerar um documento JSON estruturado contendo estritamente os dados do titular
    autenticado na sessão web corrente, garantindo total isolamento multi-tenant.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Um desenvolvedor ou IA pode relaxar os filtros da extração do dossiê ou incluir chaves de API
    e credenciais privadas no JSON exportado, violando o princípio da minimização.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    O download em formato JSON possui 'content-disposition' de anexo e contém com fidelidade
    as informações do dossiê do usuário autenticado.
    """
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
    """
    VETOR DE AMEAÇA: LGPD Art. 18, VI / CWE-212 (Improper Removal of Sensitive Information).
    Falha na eliminação completa de dados pessoais ou persistência indevida de sessão após
    solicitação de encerramento e exclusão de conta pelo titular.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    A rota DEVE acionar a cascata transacional de exclusão definitiva no banco de dados e provedor
    de autenticação, limpando o cookie de sessão e redirecionando o usuário.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Um desenvolvedor ou IA pode simplificar a rota executando apenas logout superficial
    sem orquestrar o expurgo dos registros e credenciais do usuário.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    A chamada ao endpoint invoca 'delete_user_account(MOCK_WEB_USER)' de forma assíncrona
    e redireciona para a home com mensagem de conta excluída.
    """
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


@pytest.mark.asyncio
async def test_guardrail_settings_quick_model_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """
    VETOR DE AMEAÇA: CWE-306 (Missing Authentication for Critical Function).
    Tentativa de modificação de parâmetros de IA e nível de raciocínio sem credenciais autenticadas.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    A rota POST /settings/quick-model DEVE rejeitar requisições sem cookie de sessão com HTTP 401 e payload JSON.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Qualquer tentativa de relaxar a autenticação nesta rota abriria vetores de manipulação não autorizada de configurações.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    Acesso anônimo a POST /settings/quick-model responde obrigatoriamente com status 401 e status="error".
    """
    res = await async_client.post(
        "/settings/quick-model",
        data={"model_choice": "gemini-3.8-flash:low"},
    )
    assert res.status_code == 401
    data = res.json()
    assert data["status"] == "error"
    assert "Autenticação necessária" in data["message"]


@pytest.mark.asyncio
async def test_settings_quick_model_creates_settings_success(
    async_client: AsyncClient,
) -> None:
    """Valida criação e persistência das configurações de modelo rápido."""
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
            "/settings/quick-model",
            data={"model_choice": "gemini-3.8-flash:high"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["model"] == "gemini-3.8-flash"
        assert data["thinking_level"] == "high"
        mock_add.assert_called_once()
        mock_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_settings_quick_model_updates_existing_settings_success(
    async_client: AsyncClient,
) -> None:
    """Valida atualização de modelo e thinking_level para configurações existentes."""
    async_client.cookies.set("session_token", "valid_session_token")
    existing_settings = UserSettings(
        user_id=MOCK_USER_ID,
        gemini_model="gemini-3.7-flash",
        gemini_thinking_level="medium",
    )
    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = existing_settings

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
            "/settings/quick-model",
            data={"model_choice": "gemini-3.8-flash:low"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["model"] == "gemini-3.8-flash"
        assert data["thinking_level"] == "low"
        assert existing_settings.gemini_model == "gemini-3.8-flash"
        assert existing_settings.gemini_thinking_level == "low"
        mock_commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_settings_quick_model_defaults_thinking_level(
    async_client: AsyncClient,
) -> None:
    """Valida que ausência ou valor inválido de thinking_level assume 'medium'."""
    async_client.cookies.set("session_token", "valid_session_token")
    existing_settings = UserSettings(
        user_id=MOCK_USER_ID,
        gemini_model="gemini-3.8-flash",
        gemini_thinking_level="high",
    )
    mock_db_settings = MagicMock()
    mock_db_settings.scalar_one_or_none.return_value = existing_settings

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
        patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock),
    ):
        res = await async_client.post(
            "/settings/quick-model",
            data={"model_choice": "gemini-3.7-flash:invalid"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["model"] == "gemini-3.7-flash"
        assert data["thinking_level"] == "medium"
        assert existing_settings.gemini_model == "gemini-3.7-flash"
        assert existing_settings.gemini_thinking_level == "medium"


@pytest.mark.asyncio
async def test_guardrail_settings_tokens_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """VETOR DE AMEAÇA: Acesso não autenticado a telemetria de consumo de tokens (CWE-306).
    Um invasor não autenticado ou ator não autorizado poderia mapear a atividade de uso
    de IA e scraping de quotas da plataforma.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    A rota GET /settings/tokens deve rejeitar estritamente qualquer requisição sem sessão
    ativa com HTTP 401 Unauthorized e payload de erro em JSON.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Se um desenvolvedor ou agente IA tornar o endpoint público ou afrouxar a dependência
    get_authenticated_web_user para None opcional sem verificação, métricas sensíveis de
    consumo vazariam publicamente.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    A resposta sem cookie de sessão deve retornar impreterivelmente status_code == 401
    com mensagem de erro clara.
    """
    res = await async_client.get("/settings/tokens")
    assert res.status_code == 401
    data = res.json()
    assert data["status"] == "error"
    assert "Autenticação necessária" in data["message"]


@pytest.mark.asyncio
async def test_settings_tokens_authenticated_success(
    async_client: AsyncClient,
) -> None:
    """Valida retorno bem-sucedido de métricas de tokens para usuário autenticado."""
    async_client.cookies.set("session_token", "valid_session_token")
    mock_token_data = {
        "tokens_used_today": 1200,
        "requests_used_today": 3,
        "tokens_used_total": 45000,
        "formatted_tokens_today": "1.200",
        "formatted_tokens_total": "45.000",
    }

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.token_service.get_user_token_usage",
            new_callable=AsyncMock,
            return_value=mock_token_data,
        ) as mock_get_tokens,
    ):
        res = await async_client.get("/settings/tokens")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["tokens_used_today"] == 1200
        assert data["requests_used_today"] == 3
        assert data["tokens_used_total"] == 45000
        assert data["formatted_tokens_today"] == "1.200"
        assert data["formatted_tokens_total"] == "45.000"
        mock_get_tokens.assert_awaited_once()


# ==============================================================================
# TESTES DE COBERTURA INTEGRAL DO WEB ROUTER (SPRINT 4 EXTENSION)
# ==============================================================================


@pytest.mark.asyncio
async def test_welcome_page_authenticated_routing_with_and_without_dossier(
    async_client: AsyncClient,
) -> None:
    """Valida redirecionamento inteligente do usuário autenticado na home page."""
    async_client.cookies.set("session_token", "valid_session_token")

    # 1. Usuário autenticado COM dossiê cadastrado -> /applications
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.profile_service.ProfileService.has_dossier",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        res = await async_client.get("/", follow_redirects=False)
        assert res.status_code == 302
        assert res.headers["location"] == "/applications"

    # 2. Usuário autenticado SEM dossiê cadastrado -> /profile
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.profile_service.ProfileService.has_dossier",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        res = await async_client.get("/", follow_redirects=False)
        assert res.status_code == 302
        assert res.headers["location"] == "/profile"


@pytest.mark.asyncio
async def test_web_logout_authenticated_revokes_session(async_client: AsyncClient) -> None:
    """Valida revogação da sessão no servidor ao realizar logout autenticado."""
    async_client.cookies.set("session_token", "valid_session_token")

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.auth_service.AuthService.revoke_session",
            new_callable=AsyncMock,
        ) as mock_revoke,
    ):
        res = await async_client.post("/auth/logout")
        assert res.status_code == 200
        assert res.headers.get("HX-Refresh") == "true"
        mock_revoke.assert_awaited_once_with(MOCK_WEB_USER)


@pytest.mark.asyncio
async def test_web_profile_page_access_unauthenticated_and_authenticated(
    async_client: AsyncClient,
) -> None:
    """Valida acesso anônimo (redirect) e autenticado à página de dossiê profissional."""
    # 1. Anônimo -> redirect
    res_anon = await async_client.get("/profile", follow_redirects=False)
    assert res_anon.status_code == 302
    assert res_anon.headers["location"] == "/?auth_error=login_required"

    # 2. Autenticado -> 200 OK com template renderizado
    async_client.cookies.set("session_token", "valid_session_token")
    mock_dossier = {
        "experiences": [],
        "educations": [],
        "certifications": [],
        "projects": [],
        "skills": [],
        "languages": [],
    }
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
    ):
        res = await async_client.get("/profile")
        assert res.status_code == 200
        assert "Dossiê Profissional" in res.text or "Repositório" in res.text or "Carla" in res.text


@pytest.mark.asyncio
async def test_web_create_resume_page_authenticated_with_error(
    async_client: AsyncClient,
) -> None:
    """Valida renderização de /resumes/new com usuário autenticado e mensagem de erro."""
    async_client.cookies.set("session_token", "valid_session_token")
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.prompt_skill_service.PromptSkillService.list_active_skills",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.token_service.get_user_token_usage",
            new_callable=AsyncMock,
            return_value={"tokens_used_today": 0},
        ),
    ):
        res = await async_client.get("/resumes/new?error=Falha+de+teste")
        assert res.status_code == 200
        assert "Falha de teste" in res.text


def test_web_extract_updated_resume_content_education_hyphen() -> None:
    """Valida parsing de período educacional com hífen tradicional (BVA)."""
    base_content = {"education": []}
    form_data = {
        "edu_0_degree": "BSc Engenharia",
        "edu_0_institution": "UFMG",
        "edu_0_field": "Computação",
        "edu_0_period": "2018 - 2022",
        "edu_1_degree": "MSc Inteligência Artificial",
        "edu_1_institution": "USP",
        "edu_1_field": "IA",
        "edu_1_period": "2023-",
    }
    updated = _extract_updated_resume_content(base_content, form_data)
    edus = updated["education"]
    assert len(edus) == 2
    assert edus[0]["start_date"] == "2018"
    assert edus[0]["end_date"] == "2022"
    assert edus[1]["start_date"] == "2023"
    assert edus[1]["end_date"] == ""


@pytest.mark.asyncio
async def test_web_preview_resume_page_with_application_notes_and_skill(
    async_client: AsyncClient,
) -> None:
    """Valida renderização do preview com notas do Copilot (prefixadas) e PromptSkill."""
    async_client.cookies.set("session_token", "valid_session_token")
    resume_id = uuid.uuid4()
    app_id = uuid.uuid4()
    skill_id = uuid.uuid4()

    mock_resume = MagicMock(spec=GeneratedResume)
    mock_resume.id = resume_id
    mock_resume.user_id = MOCK_USER_ID
    mock_resume.application_id = app_id
    mock_resume.prompt_skill_id = skill_id
    mock_resume.structured_content = {"header": {"target_title": "Security Lead"}}
    mock_resume.match_percentage = 85
    mock_resume.version_number = 1
    mock_resume.status = "draft"

    mock_application = MagicMock(spec=Application)
    mock_application.id = app_id
    mock_application.notes = []

    mock_skill = MagicMock(spec=PromptSkill)
    mock_skill.id = skill_id
    mock_skill.slug = "specialist-slug"

    notes = [
        MagicMock(content="👤 Candidato: Gostaria de enfatizar criptografia."),
        MagicMock(content="🤖 Copilot IA: Destaquei os projetos com AES-GCM."),
        MagicMock(content="🤖 Copilot: Atualização aplicada com sucesso."),
        MagicMock(content="Nota sem prefixo conhecido."),
    ]

    mock_resume_result = MagicMock()
    mock_resume_result.scalar_one_or_none.return_value = mock_resume

    mock_app_result = MagicMock()
    mock_app_result.scalar_one_or_none.return_value = mock_application

    mock_notes_result = MagicMock()
    mock_notes_result.scalars.return_value.all.return_value = notes

    mock_skill_result = MagicMock()
    mock_skill_result.scalar_one_or_none.return_value = mock_skill

    async def mock_execute(stmt: Any, *args: Any, **kwargs: Any) -> Any:
        stmt_str = str(stmt)
        if "FROM generated_resumes" in stmt_str:
            return mock_resume_result
        if "FROM applications" in stmt_str:
            return mock_app_result
        if "FROM application_notes" in stmt_str:
            return mock_notes_result
        if "FROM prompt_skills" in stmt_str:
            return mock_skill_result
        return mock_resume_result

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            side_effect=mock_execute,
        ),
        patch(
            "app.services.profile_service.ProfileService.get_full_dossier",
            new_callable=AsyncMock,
            return_value={"experiences": []},
        ),
    ):
        res = await async_client.get(f"/resumes/{resume_id}/preview")
        assert res.status_code == 200
        assert "specialist-slug" in res.text or "Security Lead" in res.text


@pytest.mark.asyncio
async def test_web_regenerate_from_chat_variations(
    async_client: AsyncClient,
) -> None:
    """Valida ramificações de erro e redirecionamento de regeração de currículo via chat."""
    async_client.cookies.set("session_token", "valid_session_token")
    resume_id = uuid.uuid4()

    # 1. history_json inválido + chat vazio + currículo não encontrado -> 404
    mock_empty_res = MagicMock()
    mock_empty_res.scalar_one_or_none.return_value = None

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_empty_res,
        ),
    ):
        res_404 = await async_client.post(
            f"/resumes/{resume_id}/regenerate-from-chat",
            data={"history_json": "invalid-json-structure", "prompt_skill_slug": "google-xyz"},
        )
        assert res_404.status_code == 404
        assert "não encontrado" in res_404.text

    valid_history = json.dumps([{"role": "user", "content": "Adicione certificação CISSP"}])

    # 2. resume_service levanta HTTPException -> repassa a exceção (ex: 400)
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.resume_service.ResumeService.regenerate_resume_from_chat",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=400, detail="Erro de validação"),
        ),
    ):
        res_http_err = await async_client.post(
            f"/resumes/{resume_id}/regenerate-from-chat",
            data={"history_json": valid_history, "prompt_skill_slug": "google-xyz"},
        )
        assert res_http_err.status_code == 400
        assert "Erro de validação" in res_http_err.text

    # 3. resume_service levanta exceção inesperada -> 500 com template
    app_id = uuid.uuid4()
    mock_resume = MagicMock(spec=GeneratedResume)
    mock_resume.id = resume_id
    mock_resume.user_id = MOCK_USER_ID
    mock_resume.application_id = app_id
    mock_resume_found = MagicMock()
    mock_resume_found.scalar_one_or_none.return_value = mock_resume

    mock_app_found = MagicMock()
    mock_app_found.scalar_one_or_none.return_value = MagicMock(spec=Application, id=app_id)

    async def mock_exec_500(stmt: Any, *args: Any, **kwargs: Any) -> Any:
        if "FROM generated_resumes" in str(stmt):
            return mock_resume_found
        return mock_app_found

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.resume_service.ResumeService.regenerate_resume_from_chat",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Falha de infraestrutura no cluster LLM"),
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            side_effect=mock_exec_500,
        ),
    ):
        res_500 = await async_client.post(
            f"/resumes/{resume_id}/regenerate-from-chat",
            data={"history_json": valid_history, "prompt_skill_slug": "google-xyz"},
        )
        assert res_500.status_code == 500
        assert "Falha na regeração da versão" in res_500.text

    # 4. Sucesso sem header HX-Request -> 303 See Other
    new_version_id = uuid.uuid4()
    mock_new_res = MagicMock()
    mock_new_res.resume_id = new_version_id

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.resume_service.ResumeService.regenerate_resume_from_chat",
            new_callable=AsyncMock,
            return_value=mock_new_res,
        ),
        patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock),
    ):
        res_303 = await async_client.post(
            f"/resumes/{resume_id}/regenerate-from-chat",
            data={"history_json": valid_history, "prompt_skill_slug": "google-xyz"},
            follow_redirects=False,
        )
        assert res_303.status_code == 303
        assert res_303.headers["location"] == f"/resumes/{new_version_id}?tab=editor"


@pytest.mark.asyncio
async def test_web_settings_variations(async_client: AsyncClient) -> None:
    """Valida validações e normalizações de modelos e níveis de pensamento em POST /settings."""
    async_client.cookies.set("session_token", "valid_session_token")

    # 1. Chave vazia sem chave cadastrada -> 400 Bad Request
    mock_none_settings = MagicMock()
    mock_none_settings.scalar_one_or_none.return_value = None

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_none_settings,
        ),
    ):
        res_blank = await async_client.post(
            "/settings/gemini-key",
            data={"gemini_api_key": ""},
        )
        assert res_blank.status_code == 400
        assert "A chave de API não pode estar em branco" in res_blank.text

    # 2. Modelo legado gemini-2.5-flash e thinking level inválido normalizados para 3.8-flash e medium
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_none_settings,
        ),
        patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock),
        patch("sqlalchemy.ext.asyncio.AsyncSession.add") as mock_db_add,
    ):
        res_norm = await async_client.post(
            "/settings/gemini-key",
            data={
                "gemini_api_key": "AIzaSyTestNewValidKey123",
                "gemini_model": "gemini-2.5-flash",
                "gemini_thinking_level": "extreme_hyper",
            },
        )
        assert res_norm.status_code == 200
        assert "salva e cifrada com sucesso" in res_norm.text
        added_obj = mock_db_add.call_args[0][0]
        assert added_obj.gemini_model == "gemini-3.8-flash"
        assert added_obj.gemini_thinking_level == "medium"

    # 3. Chave vazia com chave existente no banco -> preserva chave existente (linhas 1977-1978)
    mock_existing_settings = MagicMock()
    existing_user_settings = UserSettings(
        id=uuid.uuid4(),
        user_id=MOCK_USER_ID,
        encrypted_gemini_api_key="existing_enc_key",
        gemini_model="gemini-3.8-flash",
        gemini_thinking_level="medium",
    )
    mock_existing_settings.scalar_one_or_none.return_value = existing_user_settings

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "sqlalchemy.ext.asyncio.AsyncSession.execute",
            new_callable=AsyncMock,
            return_value=mock_existing_settings,
        ),
        patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock),
    ):
        res_preserve = await async_client.post(
            "/settings/gemini-key",
            data={
                "gemini_api_key": "",
                "gemini_model": "gemini-2.5-pro",
                "gemini_thinking_level": "high",
            },
        )
        assert res_preserve.status_code == 200
        assert "salva e cifrada com sucesso" in res_preserve.text
        assert existing_user_settings.encrypted_gemini_api_key == "existing_enc_key"
        assert existing_user_settings.gemini_model == "gemini-3.8-flash"
        assert existing_user_settings.gemini_thinking_level == "high"


@pytest.mark.asyncio
async def test_web_settings_gemini_key_test_model_unavailable(
    async_client: AsyncClient,
) -> None:
    """Valida resposta com alerta amber quando o teste de chave falha por indisponibilidade."""
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
            side_effect=ModelUnavailableError(
                "Esse modelo está temporariamente indisponível.", model="gemini-3.8-flash"
            ),
        ),
    ):
        res = await async_client.post(
            "/settings/gemini-key/test",
            data={"gemini_api_key": "AIzaSyTestKey123456789"},
        )
        assert res.status_code == 200
        assert "Esse modelo está temporariamente indisponível" in res.text
        assert "bg-amber-50" in res.text


@pytest.mark.asyncio
async def test_google_callback_with_profile_service_has_dossier() -> None:
    """Valida google_callback com profile_service determinando destino /applications."""
    auth_service_mock = MagicMock(spec=AuthService)
    user_mock = User(id=uuid.uuid4(), email="test@google.com")
    auth_service_mock.authenticate_oauth_user = AsyncMock(
        return_value=(user_mock, "jwt_token_google")
    )
    profile_mock = AsyncMock()
    profile_mock.has_dossier = AsyncMock(return_value=True)

    req = MagicMock(spec=Request)
    req.cookies = {"oauth_state": "direct_state_123"}
    resp = await google_callback(
        request=req,
        code="valid_code",
        state="direct_state_123",
        auth_service=auth_service_mock,
        profile_service=profile_mock,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/applications"
