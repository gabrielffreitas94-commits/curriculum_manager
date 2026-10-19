"""Guardrails anti-regressão de segurança contra vazamento de erros do sistema.

VETOR DE AMEAÇA:
- CWE-209: Generation of Error Message Containing Sensitive Information
- CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
- OWASP Top 10 - A05:2021 (Security Misconfiguration) / A01:2025
- OWASP API Security - API8:2023 (Security Misconfiguration)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient

from app.api.v1.deps import get_current_auth_user
from app.core.url_scraper import SSRFProtectionError
from app.domain.models import User
from app.main import create_application
from app.ports.ai_port import AIError, AIPort, ChatMessage
from app.ports.auth_port import AuthError, InvalidTokenError
from app.services.copilot_service import CopilotService
from app.services.job_ingest_service import JobIngestService


@pytest.mark.asyncio
async def test_guardrail_500_internal_error_never_leaks_sensitive_details_json() -> None:
    """Valida que exceções não tratadas 500 NUNCA vazam dados sensíveis ou stack traces em JSON.

    VETOR DE AMEAÇA:
    - CWE-209 / OWASP A05:2021 (Security Misconfiguration).
    - Impacto: Atacantes obtêm credenciais de banco de dados, topologia de rede interna
      ou stack traces detalhados que facilitam explorações direcionadas.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O manipulador global de exceções DEVE capturar qualquer erro 500 não tratado e retornar
      uma mensagem estritamente genérica e padronizada em formato JSON.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Um refactoring no ciclo de vida do FastAPI ou a remoção do exception_handler global
      faria o Starlette/FastAPI recorrer a fallbacks que expõem stack traces completos ou
      mensagens internas de bibliotecas.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - A resposta HTTP DEVE ser exatamente 500 e o payload JSON DEVE conter apenas a mensagem
      genérica segura, sem qualquer menção aos termos sensíveis da exceção disparada.
    """
    app = create_application()

    @app.get("/test-unhandled-crash")
    async def crash_endpoint() -> None:
        raise RuntimeError(
            "Database connection failed: postgresql://admin:supersecret@10.0.1.50:5432/thothdb"
        )

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/test-unhandled-crash",
            headers={"Accept": "application/json"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert (
            data["detail"]
            == "Ocorreu um erro interno no servidor. Por favor, tente novamente mais tarde."
        )
        assert "supersecret" not in response.text
        assert "10.0.1.50" not in response.text
        assert "postgresql" not in response.text
        assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_guardrail_500_internal_error_never_leaks_sensitive_details_html() -> None:
    """Valida que exceções não tratadas 500 NUNCA vazam detalhes técnicos em respostas HTML.

    VETOR DE AMEAÇA:
    - CWE-209 / CWE-79: Exposição de erros do sistema e potencial XSS via injeção em templates.
    - Impacto: Vazamento de caminhos de arquivos no servidor (/etc/shadow, paths de aplicação).

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Requisições web navegáveis (Accept: text/html) DEVEM receber um container HTML seguro
      com mensagem amigável, sem detalhamento de exceções.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Deixar a exceção subir sem tratamento renderizaria telas de debug do Uvicorn ou
      mensagens cruas no frontend.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - A resposta DEVE ser 500 e o corpo HTML NÃO PODE conter caminhos do sistema operacional
      ou mensagens cruas da exceção.
    """
    app = create_application()

    @app.get("/test-web-crash")
    async def web_crash_endpoint() -> None:
        raise FileNotFoundError("/var/run/secrets/kubernetes.io/serviceaccount/token not found")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/test-web-crash",
            headers={"Accept": "text/html"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "serviceaccount" not in response.text
        assert "/var/run/secrets" not in response.text
        assert "Ocorreu um erro interno no servidor" in response.text


@pytest.mark.asyncio
async def test_guardrail_5xx_http_exception_sanitized() -> None:
    """Valida que HTTPException com status >= 500 é sanitizada pelo manipulador global.

    VETOR DE AMEAÇA:
    - CWE-209: Desenvolvedores levantando HTTPException(500, detail=str(internal_exc)).
    - Impacto: Vazamento inadvertido de diagnósticos confidenciais de infraestrutura.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Toda HTTPException com código 5xx DEVE ter seu detail sanitizado para o cliente,
      enquanto o log do servidor armazena o detalhe original.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Suportar detail customizado em erros 5xx reabre o canal de vazamento de credenciais.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Resposta 500 deve ocultar qualquer detalhe técnico sensível repassado no parâmetro detail.
    """
    app = create_application()

    @app.get("/test-http-500")
    async def http_500_endpoint() -> None:
        raise HTTPException(
            status_code=500,
            detail="Falha crítica de descriptografia: AES-GCM tag mismatch on key_id=0xFA12",
        )

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/test-http-500",
            headers={"Accept": "application/json"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert (
            data["detail"]
            == "Ocorreu um erro interno no servidor. Por favor, tente novamente mais tarde."
        )
        assert "AES-GCM" not in response.text
        assert "key_id" not in response.text


@pytest.mark.asyncio
async def test_guardrail_5xx_http_exception_sanitized_html() -> None:
    """Valida que HTTPException 5xx para clientes HTML retorna container amigável sem vazar detalhes.

    VETOR DE AMEAÇA:
    - CWE-209: Exposição de erros internos em respostas navegáveis.
    - Impacto: Vazamento de arquitetura interna e segredos no DOM.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Retornar status 500 com HTML seguro contendo mensagem padronizada.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Renderizar o detail do erro no HTML expõe diagnósticos.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - O corpo da resposta deve conter apenas mensagem segura e não vazar a string sensível.
    """
    app = create_application()

    @app.get("/test-html-500")
    async def html_500_endpoint() -> None:
        raise HTTPException(status_code=500, detail="Database leaked secret")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/test-html-500", headers={"Accept": "text/html"})
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Database leaked secret" not in response.text
        assert "Ocorreu um erro interno no servidor" in response.text


@pytest.mark.asyncio
async def test_guardrail_4xx_http_exception_escaped_html() -> None:
    """Valida que exceções 4xx em requisições HTML sofrem escape estrito contra XSS.

    VETOR DE AMEAÇA:
    - CWE-79: Cross-Site Scripting via reflexão de mensagens de validação não escapadas.
    - Impacto: Execução de scripts no contexto do navegador do usuário.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O conteúdo retornado no HTML DEVE ser devidamente escapado com html.escape.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Interpolação f-string crua de exc.detail no HTML reabre a vulnerabilidade XSS.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Tags <script> DEVEM ser neutralizadas para &lt;script&gt;.
    """
    app = create_application()

    @app.get("/test-html-400")
    async def html_400_endpoint() -> None:
        raise HTTPException(status_code=400, detail="<script>alert('xss')</script>")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/test-html-400", headers={"Accept": "text/html"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "<script>" not in response.text
        assert "&lt;script&gt;" in response.text


@pytest.mark.asyncio
async def test_guardrail_auth_exceptions_never_leak_jwt_internals() -> None:
    """Valida que erros de token em deps.py NUNCA vazam detalhes de criptografia ou validação JWT.

    VETOR DE AMEAÇA:
    - CWE-209 / CWE-287: Improper Authentication & Information Disclosure.
    - Impacto: Revelar aos atacantes algoritmos esperados, chaves públicas, bibliotecas
      ou motivos exatos de rejeição criptográfica de tokens forjados.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Retornar estritamente HTTP 401 com mensagem genérica "Credencial de autenticação inválida ou expirada."
      sem concatenar str(exc).

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Concatenação f'Credencial inválida: {exc}' reabre o vazamento de detalhes do PyJWT/Firebase.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - O detail da HTTPException DEVE ser idêntico à mensagem genérica padronizada.
    """
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="attacker_token")

    with patch("app.api.v1.deps.auth_adapter.verify_token") as mock_verify:
        mock_verify.side_effect = InvalidTokenError(
            "JWT signature failed: expected RS256 with key e=65537"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_auth_user(credentials=creds)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Credencial de autenticação inválida ou expirada."
        assert "RS256" not in exc_info.value.detail
        assert "65537" not in exc_info.value.detail

    with patch("app.api.v1.deps.auth_adapter.verify_token") as mock_verify:
        mock_verify.side_effect = AuthError(
            "Firebase JWKS endpoint connection timeout to https://googleapis.internal"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_auth_user(credentials=creds)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Falha de autenticação."
        assert "googleapis.internal" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_guardrail_ssrf_error_never_leaks_private_network_topology() -> None:
    """Valida que erros de SSRF em JobIngestService NUNCA revelam IPs privados ou rotas internas.

    VETOR DE AMEAÇA:
    - CWE-918 (SSRF) & CWE-209 (Information Disclosure).
    - Impacto: O atacante descobre a faixa de IP de sub-redes internas e metadados de nuvem
      através do feedback de erro.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Lançar HTTP 400 com mensagem segura genérica, sem expor IPs ou hostnames bloqueados.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Retornar f'Acesso bloqueado por segurança: {exc}' informa ao invasor o IP bloqueado.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - O detail retornado NUNCA deve conter o IP ou o motivo exato disparado pela camada core.
    """
    service = JobIngestService()

    with patch(
        "app.services.job_ingest_service.safe_fetch_url", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.side_effect = SSRFProtectionError(
            "IP privado 169.254.169.254 bloqueado por apontar para Cloud Metadata"
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.extract_text_from_url("http://169.254.169.254/latest/meta-data")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "169.254.169.254" not in exc_info.value.detail
        assert "Cloud Metadata" not in exc_info.value.detail
        assert (
            exc_info.value.detail
            == "Acesso bloqueado por segurança. O endereço informado não é permitido."
        )


@pytest.mark.asyncio
async def test_guardrail_copilot_service_upstream_failure_never_leaks_raw_exception() -> None:
    """Valida que falhas upstream da Google Gemini API no CopilotService não expõem detalhes de erro de IA.

    VETOR DE AMEAÇA:
    - CWE-209: Exposição de quotas, limites, modelos ou tokens de API em respostas de IA.
    - Impacto: Ataques de enumeração e exploração de limites de recursos de LLM.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Mapear falhas de comunicação para HTTP 502 com mensagem genérica segura.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Concatenação f'Falha na comunicação com o Copilot de IA: {exc}' revela a mensagem bruta do SDK.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - O detail da exceção DEVE ser a mensagem genérica estrita.
    """
    mock_db = AsyncMock()
    mock_ai = AsyncMock(spec=AIPort)
    mock_ai.chat_tailoring.side_effect = AIError(
        "ResourceExhausted: 429 Resource has been exhausted (quota exceeded for quota_group:GeminiFree)"
    )

    user = User(
        firebase_uid="uid-leak-test",
        email="leak@example.com",
        full_name="Leak Tester",
    )

    service = CopilotService(mock_db, mock_ai)

    with (
        patch(
            "app.services.copilot_service.ProfileService.get_full_dossier", new_callable=AsyncMock
        ) as mock_dossier,
        patch(
            "app.services.copilot_service.PromptSkillService.get_by_slug", new_callable=AsyncMock
        ) as mock_skill,
    ):
        mock_dossier.return_value = {
            "experiences": [],
            "skills": [],
            "projects": [],
            "educations": [],
            "certifications": [],
        }
        mock_skill.return_value = MagicMock(system_prompt="Instruções")

        with pytest.raises(HTTPException) as exc_info:
            await service.chat(
                user=user,
                job_description="Engenheiro Backend",
                prompt_skill_slug="google-xyz",
                messages=[ChatMessage(role="user", content="Ajuda")],
            )

    assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert "ResourceExhausted" not in exc_info.value.detail
    assert "quota_group" not in exc_info.value.detail
    assert (
        exc_info.value.detail
        == "Falha na comunicação com o Copilot de IA. Tente novamente mais tarde."
    )
