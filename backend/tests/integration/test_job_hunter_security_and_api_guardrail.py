"""Testes de integração e guardrails anti-regressão de segurança para o Job Hunter API.

Cobre a rota POST /api/v1/job-hunter/hunt garantindo:
1. Blindagem fail-closed contra Server-Side Request Forgery (SSRF - CWE-918).
2. Rigoroso isolamento multi-tenant de candidaturas e notificações (BOLA - CWE-639).
3. Prevenção contra DoS por lote excessivo e resiliência a rate limit / bloqueios upstream (CWE-400/770).
4. Rejeição fail-closed de requisições não autenticadas ou com tokens corrompidos (CWE-306).
"""

import socket
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import crypto_service
from app.core.url_scraper import validate_target_url
from app.domain.models import Application, Notification, Skill, User, UserSettings
from app.ports.ai_port import JobAnalysisResult
from app.ports.auth_port import AuthUser, InvalidTokenError
from app.ports.job_hunter_port import JobSourceBlockedError, JobSourceRateLimitError

# Identificadores determinísticos para os testes de integração
USER_SSRF_ID = uuid.uuid4()
USER_A_ID = uuid.uuid4()
USER_B_ID = uuid.uuid4()
USER_RESILIENCE_ID = uuid.uuid4()

AUTH_USER_SSRF = AuthUser(
    uid="user_ssrf_guardrail",
    email="ssrf_guardrail@example.com",
    full_name="SSRF Guardrail Auditor",
)

AUTH_USER_A = AuthUser(
    uid="user_tenant_a",
    email="tenant_a@example.com",
    full_name="Tenant A Auditor",
)

AUTH_USER_B = AuthUser(
    uid="user_tenant_b",
    email="tenant_b@example.com",
    full_name="Tenant B Auditor",
)

AUTH_USER_RESILIENCE = AuthUser(
    uid="user_resilience",
    email="resilience@example.com",
    full_name="Resilience Auditor",
)


def _mock_verify_token(token: str) -> AuthUser:
    """Validador determinístico de tokens para isolamento estrito de usuários nos testes."""
    token_mapping = {
        "token_ssrf_guardrail": AUTH_USER_SSRF,
        "token_tenant_a": AUTH_USER_A,
        "token_tenant_b": AUTH_USER_B,
        "token_resilience": AUTH_USER_RESILIENCE,
    }
    if token in token_mapping:
        return token_mapping[token]
    raise InvalidTokenError(f"Token de teste não autorizado ou inválido: '{token}'.")


@pytest.fixture
async def setup_guardrail_users(db_session: AsyncSession) -> dict[str, Any]:
    """Cria os usuários, configurações de IA criptografadas e competências para os testes."""
    users_data = [
        (USER_SSRF_ID, "user_ssrf_guardrail", "ssrf_guardrail@example.com", "SSRF Auditor"),
        (USER_A_ID, "user_tenant_a", "tenant_a@example.com", "Tenant A Auditor"),
        (USER_B_ID, "user_tenant_b", "tenant_b@example.com", "Tenant B Auditor"),
        (USER_RESILIENCE_ID, "user_resilience", "resilience@example.com", "Resilience Auditor"),
    ]

    for uid_val, fb_uid, email_val, name_val in users_data:
        user = User(
            id=uid_val,
            firebase_uid=fb_uid,
            email=email_val,
            full_name=name_val,
        )
        db_session.add(user)
        await db_session.flush()

        settings = UserSettings(
            user_id=user.id,
            encrypted_gemini_api_key=crypto_service.encrypt(
                "AIzaSyMockKeyForJobHunterSecurityTesting",
                associated_data=str(user.id).encode("utf-8"),
            ),
        )
        db_session.add(settings)

        # Adiciona competências essenciais para match semântico positivo
        s1 = Skill(id=uuid.uuid4(), user_id=user.id, name="Python", category="Backend")
        s2 = Skill(id=uuid.uuid4(), user_id=user.id, name="FastAPI", category="Backend")
        s3 = Skill(id=uuid.uuid4(), user_id=user.id, name="Docker", category="DevOps")
        db_session.add_all([s1, s2, s3])

    await db_session.commit()

    return {
        "user_ssrf_id": USER_SSRF_ID,
        "user_a_id": USER_A_ID,
        "user_b_id": USER_B_ID,
        "user_resilience_id": USER_RESILIENCE_ID,
        "headers_ssrf": {"Authorization": "Bearer token_ssrf_guardrail"},
        "headers_a": {"Authorization": "Bearer token_tenant_a"},
        "headers_b": {"Authorization": "Bearer token_tenant_b"},
        "headers_resilience": {"Authorization": "Bearer token_resilience"},
    }


@pytest.mark.asyncio
async def test_job_hunter_ssrf_protection_fail_closed_guardrail(
    async_client: AsyncClient,
    setup_guardrail_users: dict[str, Any],
) -> None:
    """Valida a blindagem fail-closed contra Server-Side Request Forgery em lote no Job Hunter.

    VETOR DE AMEAÇA:
    - CWE-918 (Server-Side Request Forgery) / OWASP A10:2021 (SSRF) / STRIDE: Tampering & Information Disclosure.
    - Impacto Potencial: O atacante injeta URLs de serviços de metadados de provedores de nuvem
      (http://169.254.169.254/latest/meta-data/) ou endpoints locais internos (http://127.0.0.1:8080/admin)
      em um lote de vagas para extrair credenciais efêmeras de IAM ou acessar APIs internas desprotegidas.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O sistema DEVE interceptar e rejeitar sumariamente qualquer endereço de loopback ou metadados de nuvem.
    - As URLs internas DEVEM ser marcadas como decision="failed_source" e error_code="SSRF_BLOCKED",
      sem realizar tentativas de retry nem repassar o conteúdo ou URLs para o adaptador de IA.
    - O erro DEVE ser isolado por fonte: a URL legítima presente no mesmo lote ("https://jobs.example.com/legitimate-engineer")
      DEVE ser processada com sucesso (pre_applied_count=1, failed_count=2), garantindo resiliência operacional.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Um desenvolvedor ou agente IA poderia supor que a validação de URLs no orquestrador é redundante
      e removê-la, ou usar clientes HTTP que seguem redirects para endereços locais sem validar o IP de destino.
    - Uma alteração incorreta poderia abortar todo o lote em caso de erro individual ou, pior, ignorar
      o erro de SSRF e tentar invocar o modelo de linguagem com URLs internas.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Oráculo de Rejeição SSRF: error_code="SSRF_BLOCKED", decision="failed_source" e failed_count=2.
    - Oráculo de Sucesso Legítimo: pre_applied_count=1 e decision="pre_applied" com application_id não nulo.
    - Oráculo Comportamental (Spy de IA): ai_port.analyze_job chamado exatamente UMA vez (apenas para a vaga legítima)
      e NUNCA para os alvos internos (169.254.169.254 ou 127.0.0.1).
    """
    headers = setup_guardrail_users["headers_ssrf"]

    # Simula resolução de DNS para jobs.example.com retornando IP público seguro (RFC 2606)
    orig_getaddrinfo = socket.getaddrinfo

    def custom_getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any) -> Any:
        if host == "jobs.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        return orig_getaddrinfo(host, port, *args, **kwargs)

    # Executa a validação real de SSRF (validate_target_url) e retorna HTML apenas para o host público
    async def monitored_safe_fetch(url: str, **kwargs: Any) -> str:
        validate_target_url(url)
        return (
            "Empresa: Acme Tech\n"
            "Vaga: Senior Python Engineer\n"
            "Requisitos: Python, FastAPI\n"
            "Modelo: remote\n"
            "Descricao: Oportunidade para atuar no desenvolvimento de APIs de alta escala."
        )

    mock_analysis = JobAnalysisResult(
        job_title="Senior Python Engineer",
        seniority_level="Senior",
        mandatory_requirements=["Python", "FastAPI"],
        desirable_requirements=["Docker"],
        keywords=["Python", "FastAPI", "Docker"],
    )
    mock_ai = AsyncMock(return_value=mock_analysis)

    batch_payload = {
        "source_urls": [
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1:8080/admin",
            "https://jobs.example.com/legitimate-engineer",
        ],
        "auto_pre_apply": True,
        "min_match_score": 50.0,
    }

    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", side_effect=_mock_verify_token),
        patch("socket.getaddrinfo", side_effect=custom_getaddrinfo),
        patch("app.adapters.job_source_adapter.safe_fetch_url", side_effect=monitored_safe_fetch),
        patch("app.adapters.gemini_ai_adapter.GeminiAIAdapter.analyze_job", mock_ai),
    ):
        response = await async_client.post(
            "/api/v1/job-hunter/hunt",
            headers=headers,
            json=batch_payload,
        )

    # 1. Validação de status HTTP e agregação do lote
    assert response.status_code == 200, f"Falha na resposta do endpoint: {response.text}"
    data = response.json()
    assert data["total_sources"] == 3
    assert data["failed_count"] == 2
    assert data["pre_applied_count"] == 1
    assert data["processed_count"] == 1
    assert data["skipped_duplicate_count"] == 0

    results = data["results"]
    assert len(results) == 3

    # 2. Oráculo estrito para URLs internas bloqueadas
    res_169 = results[0]
    assert res_169["source_url"] == "http://169.254.169.254/latest/meta-data/"
    assert res_169["decision"] == "failed_source"
    assert res_169["error_code"] == "SSRF_BLOCKED"
    assert "anti-SSRF" in res_169["reason"]
    assert res_169["application_id"] is None

    res_127 = results[1]
    assert res_127["source_url"] == "http://127.0.0.1:8080/admin"
    assert res_127["decision"] == "failed_source"
    assert res_127["error_code"] == "SSRF_BLOCKED"
    assert "anti-SSRF" in res_127["reason"]
    assert res_127["application_id"] is None

    # 3. Oráculo estrito para a oportunidade legítima
    res_legit = results[2]
    assert res_legit["source_url"] == "https://jobs.example.com/legitimate-engineer"
    assert res_legit["decision"] == "pre_applied"
    assert res_legit["error_code"] is None
    assert res_legit["match_percentage"] == 100.0
    assert res_legit["application_id"] is not None

    # 4. Oráculo comportamental de encaminhamento (Spy de IA)
    assert mock_ai.call_count == 1
    analyzed_text = str(mock_ai.call_args[0][0])
    assert "169.254.169.254" not in analyzed_text
    assert "127.0.0.1" not in analyzed_text
    assert "Acme Tech" in analyzed_text


@pytest.mark.asyncio
async def test_job_hunter_cross_tenant_isolation_guardrail(
    async_client: AsyncClient,
    db_session: AsyncSession,
    setup_guardrail_users: dict[str, Any],
) -> None:
    """Valida o rigoroso isolamento multi-tenant de candidaturas e detecção de duplicidade.

    VETOR DE AMEAÇA:
    - CWE-639 (Authorization Bypass Through User-Controlled Key) / OWASP API1:2023 (Broken Object Level Authorization - BOLA) / STRIDE: Elevation of Privilege & Information Disclosure.
    - Impacto Potencial: Vazamento cruzado de status de candidaturas entre tenants. Se o filtro de duplicidade
      não for escopado por user_id, o fato de o Usuário A já ter aplicado a uma vaga impediria indevidamente
      o Usuário B de aplicar, vazando a informação de que a vaga já foi reivindicada por outro usuário da plataforma.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O sistema DEVE isolar rigorosamente as candidaturas por tenant (user_id).
    - Se o Usuário A já aplicou para "https://jobs.example.com/shared-opportunity", o Usuário B DEVE poder
      executar o Job Hunter sobre a mesma URL sem sofrer rejeição por "skipped_duplicate".
    - A candidatura criada para o Usuário B e a respectiva notificação DEVEM pertencer exclusivamente a user_b.id,
      mantendo os registros do Usuário A completamente inalterados.
    - Caso o Usuário B repita a requisição, o sistema DEVE detectar duplicidade estritamente dentro do seu próprio escopo.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Um desenvolvedor poderia tentar criar um índice único global em `Application.job_url` ou simplificar
      a query `_is_duplicate_application` removendo `Application.user_id == user_id`.
    - Isso quebraria o isolamento multi-tenant e geraria contenção indevida entre usuários concorrentes.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Oráculo de Isolamento: Usuário B recebe decision="pre_applied" e pre_applied_count=1 mesmo após User A ter aplicado.
    - Oráculo de Banco de Dados: Registros de Application e Notification pertencem exclusivamente a cada respectivo user_id.
    - Oráculo Intra-Tenant: Segunda execução do Usuário B marca decision="skipped_duplicate" e skipped_duplicate_count=1.
    """
    user_a_id = setup_guardrail_users["user_a_id"]
    user_b_id = setup_guardrail_users["user_b_id"]
    headers_b = setup_guardrail_users["headers_b"]

    shared_job_url = "https://jobs.example.com/shared-opportunity"

    # 1. Usuário A já possui previamente uma candidatura salva para a mesma vaga
    prior_app_a = Application(
        id=uuid.uuid4(),
        user_id=user_a_id,
        company_name="Enterprise Global",
        job_title="Staff Systems Architect",
        job_url=shared_job_url,
        job_description="Requisitos: Python, FastAPI e Cloud Architecture.",
        work_model="remote",
        status="applied",
    )
    db_session.add(prior_app_a)
    await db_session.commit()

    # Mocks para ingestão e IA
    orig_getaddrinfo = socket.getaddrinfo

    def custom_getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any) -> Any:
        if host == "jobs.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        return orig_getaddrinfo(host, port, *args, **kwargs)

    async def fake_safe_fetch(url: str, **kwargs: Any) -> str:
        return (
            "Empresa: Enterprise Global\n"
            "Vaga: Staff Systems Architect\n"
            "Requisitos: Python, FastAPI\n"
            "Modelo: remote\n"
            "Descricao: Oportunidade corporativa em sistemas distribuídos."
        )

    mock_analysis = JobAnalysisResult(
        job_title="Staff Systems Architect",
        seniority_level="Staff",
        mandatory_requirements=["Python", "FastAPI"],
        desirable_requirements=[],
        keywords=["Python", "FastAPI"],
    )
    mock_ai = AsyncMock(return_value=mock_analysis)

    # 2. Usuário B executa o Job Hunter sobre a mesma oportunidade
    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", side_effect=_mock_verify_token),
        patch("socket.getaddrinfo", side_effect=custom_getaddrinfo),
        patch("app.adapters.job_source_adapter.safe_fetch_url", side_effect=fake_safe_fetch),
        patch("app.adapters.gemini_ai_adapter.GeminiAIAdapter.analyze_job", mock_ai),
    ):
        res_b = await async_client.post(
            "/api/v1/job-hunter/hunt",
            headers=headers_b,
            json={
                "source_urls": [shared_job_url],
                "auto_pre_apply": True,
                "min_match_score": 60.0,
            },
        )

    assert res_b.status_code == 200, f"Falha na requisição do Usuário B: {res_b.text}"
    data_b = res_b.json()
    assert data_b["total_sources"] == 1
    assert data_b["pre_applied_count"] == 1
    assert data_b["skipped_duplicate_count"] == 0
    assert data_b["results"][0]["decision"] == "pre_applied"
    user_b_app_id = uuid.UUID(data_b["results"][0]["application_id"])

    # 3. Verificação no banco de dados do isolamento absoluto de dados
    apps_a_res = await db_session.execute(
        select(Application).where(Application.user_id == user_a_id)
    )
    apps_a = apps_a_res.scalars().all()
    assert len(apps_a) == 1
    assert apps_a[0].id == prior_app_a.id
    assert apps_a[0].status == "applied"

    apps_b_res = await db_session.execute(
        select(Application).where(Application.user_id == user_b_id)
    )
    apps_b = apps_b_res.scalars().all()
    assert len(apps_b) == 1
    assert apps_b[0].id == user_b_app_id
    assert apps_b[0].user_id == user_b_id
    assert apps_b[0].job_url == shared_job_url

    notifs_a_res = await db_session.execute(
        select(Notification).where(Notification.user_id == user_a_id)
    )
    assert len(notifs_a_res.scalars().all()) == 0, "Notificação vazou para o Usuário A!"

    notifs_b_res = await db_session.execute(
        select(Notification).where(Notification.user_id == user_b_id)
    )
    notifs_b = notifs_b_res.scalars().all()
    assert len(notifs_b) == 1
    assert notifs_b[0].user_id == user_b_id
    assert notifs_b[0].application_id == user_b_app_id

    # 4. Segunda execução do Usuário B na mesma URL -> Deve detectar duplicidade estritamente no seu tenant
    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", side_effect=_mock_verify_token),
        patch("socket.getaddrinfo", side_effect=custom_getaddrinfo),
        patch("app.adapters.job_source_adapter.safe_fetch_url", side_effect=fake_safe_fetch),
        patch("app.adapters.gemini_ai_adapter.GeminiAIAdapter.analyze_job", mock_ai),
    ):
        res_b_dup = await async_client.post(
            "/api/v1/job-hunter/hunt",
            headers=headers_b,
            json={
                "source_urls": [shared_job_url],
                "auto_pre_apply": True,
                "min_match_score": 60.0,
            },
        )

    assert res_b_dup.status_code == 200
    data_b_dup = res_b_dup.json()
    assert data_b_dup["skipped_duplicate_count"] == 1
    assert data_b_dup["pre_applied_count"] == 0
    assert data_b_dup["results"][0]["decision"] == "skipped_duplicate"
    assert "já cadastrada no funil ATS" in data_b_dup["results"][0]["reason"]


@pytest.mark.asyncio
async def test_job_hunter_batch_dos_and_rate_limit_resilience_guardrail(
    async_client: AsyncClient,
    setup_guardrail_users: dict[str, Any],
) -> None:
    """Valida a mitigação de DoS por lotes excessivos e resiliência a rate limit / bloqueios upstream.

    VETOR DE AMEAÇA:
    - CWE-400 (Uncontrolled Resource Consumption) / CWE-770 (Allocation of Resources Without Limits or Throttling) / STRIDE: Denial of Service.
    - Impacto Potencial: Um usuário envia lotes de dezenas ou centenas de URLs para amplificar requisições assíncronas,
      provocando esgotamento de conexões, memória e estouro de cota da API do Gemini. Alternativamente, respostas
      upstream de Rate Limit (HTTP 429) ou WAF Block (HTTP 403) poderiam propagar exceções não tratadas (HTTP 500)
      vazando stacktraces do backend.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Payloads contendo 0 URLs ou mais de 10 URLs DEVEM ser rejeitados imediatamente na borda da API com
      HTTP 422 Unprocessable Entity, sem acionar scraper ou IA.
    - Quando fontes upstream responderem com JobSourceRateLimitError ou JobSourceBlockedError, o orquestrador
      DEVE responder HTTP 200 de forma resiliente, registrando os itens como decision="failed_source" e
      error_code="RATE_LIMITED" / "SOURCE_BLOCKED", sem quebrar o lote e sem vazar stacktraces ou nomes de classes.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Um desenvolvedor poderia afrouxar os validadores min_length e max_length do schema JobHunterGoalConfig
      para permitir "lotes maiores", abrindo o backend para exaustão de recursos.
    - Poderia remover o tratamento específico de JobSourceRateLimitError/JobSourceBlockedError do service,
      fazendo o endpoint falhar com 500 Internal Server Error e derrubando toda a esteira.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Oráculo de DoS: status HTTP 422 estrito para payloads com 0 URLs e 11 URLs, com zero invocações de scraper/IA.
    - Oráculo de Resiliência: status HTTP 200 estrito com failed_count=2, error_code="RATE_LIMITED" e "SOURCE_BLOCKED",
      e validação negativa absoluta contra "Traceback", "JobSourceRateLimitError" e "JobSourceBlockedError".
    """
    headers = setup_guardrail_users["headers_resilience"]

    mock_scraper_spy = AsyncMock()
    mock_ai_spy = AsyncMock()

    # Cenário A: Validação de Borda contra Batch Amplification DoS (>10 URLs)
    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", side_effect=_mock_verify_token),
        patch("app.adapters.job_source_adapter.safe_fetch_url", mock_scraper_spy),
        patch("app.adapters.gemini_ai_adapter.GeminiAIAdapter.analyze_job", mock_ai_spy),
    ):
        # 1. Zero URLs
        res_empty = await async_client.post(
            "/api/v1/job-hunter/hunt",
            headers=headers,
            json={"source_urls": []},
        )
        assert res_empty.status_code == 422, (
            f"Esperava 422 para lote vazio, obteve: {res_empty.status_code}"
        )

        # 2. Onze URLs (excede limite máximo seguro de 10)
        res_overflow = await async_client.post(
            "/api/v1/job-hunter/hunt",
            headers=headers,
            json={"source_urls": [f"https://example.com/jobs/{i}" for i in range(11)]},
        )
        assert res_overflow.status_code == 422, (
            f"Esperava 422 para 11 URLs, obteve: {res_overflow.status_code}"
        )

        # Comprova que a validação de borda impediu qualquer execução downstream
        assert mock_scraper_spy.call_count == 0
        assert mock_ai_spy.call_count == 0

    # Cenário B: Resiliência contra Rate Limiting (429) e Bloqueio por WAF (403) upstream
    async def resilient_source_fetch(url: str, **kwargs: Any) -> Any:
        if "rate-limited" in url:
            raise JobSourceRateLimitError("Rate limit exceeded HTTP 429 upstream.")
        if "waf-blocked" in url:
            raise JobSourceBlockedError("Access forbidden HTTP 403 Cloudflare WAF.")
        return "Empresa: Normal\nVaga: Dev\nRequisitos: Python"

    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", side_effect=_mock_verify_token),
        patch(
            "app.adapters.job_source_adapter.HttpJobSourceAdapter.fetch_job_posting",
            side_effect=resilient_source_fetch,
        ),
        patch("app.adapters.gemini_ai_adapter.GeminiAIAdapter.analyze_job", mock_ai_spy),
    ):
        res_resilience = await async_client.post(
            "/api/v1/job-hunter/hunt",
            headers=headers,
            json={
                "source_urls": [
                    "https://rate-limited.example.com/job/1",
                    "https://waf-blocked.example.com/job/2",
                ],
            },
        )

    assert res_resilience.status_code == 200, f"Falha na resiliência: {res_resilience.text}"
    data_res = res_resilience.json()
    assert data_res["total_sources"] == 2
    assert data_res["failed_count"] == 2
    assert data_res["pre_applied_count"] == 0

    results = data_res["results"]
    assert len(results) == 2

    # Validação estruturada dos erros
    res_rate = results[0]
    assert res_rate["source_url"] == "https://rate-limited.example.com/job/1"
    assert res_rate["decision"] == "failed_source"
    assert res_rate["error_code"] == "RATE_LIMITED"
    assert "rate limiting" in res_rate["reason"].lower()

    res_blocked = results[1]
    assert res_blocked["source_url"] == "https://waf-blocked.example.com/job/2"
    assert res_blocked["decision"] == "failed_source"
    assert res_blocked["error_code"] == "SOURCE_BLOCKED"
    assert "bloqueado" in res_blocked["reason"].lower()

    # Validação estrita de não-vazamento de stacktrace ou tipos de exceção no corpo
    raw_response_text = res_resilience.text
    assert "Traceback" not in raw_response_text
    assert "JobSourceRateLimitError" not in raw_response_text
    assert "JobSourceBlockedError" not in raw_response_text
    assert 'File "' not in raw_response_text


@pytest.mark.asyncio
async def test_job_hunter_unauthenticated_access_rejected_guardrail(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Valida a rejeição fail-closed de acessos anônimos ou com credenciais inválidas.

    VETOR DE AMEAÇA:
    - CWE-306 (Missing Authentication for Critical Function) / OWASP A07:2021 (Identification and Authentication Failures) / STRIDE: Spoofing & Elevation of Privilege.
    - Impacto Potencial: Um atacante anônimo invoca o endpoint de triagem autônoma para orquestrar
      buscas na rede e consumir quotas de scraping e modelos de IA generativa sem identificação de tenant.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Requisições sem o cabeçalho Authorization DEVEM ser rejeitadas sumariamente com HTTP 401 Unauthorized.
    - Requisições com token inválido, adulterado ou malformado DEVEM ser rejeitadas com HTTP 401 Unauthorized.
    - Nenhuma operação de rede, scraping, banco de dados ou consulta à IA DEVE ser disparada.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Um desenvolvedor poderia alterar o router para tornar a dependência de autenticação opcional
      (`user: User | None = Depends(...)`) visando facilitar integrações públicas, expondo o pipeline de IA.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Oráculo de Rejeição Anônima: status HTTP 401 estrito para ausência de header Authorization e para token inválido.
    - Oráculo de Isolamento: nenhuma entidade é gravada na tabela Application ou Notification.
    """
    sample_payload = {
        "source_urls": ["https://jobs.example.com/unauthenticated-test"],
        "auto_pre_apply": True,
    }

    # 1. Sem header de autenticação
    res_no_auth = await async_client.post(
        "/api/v1/job-hunter/hunt",
        json=sample_payload,
    )
    assert res_no_auth.status_code == 401, (
        f"Esperava 401 sem header, obteve: {res_no_auth.status_code}"
    )
    assert "detail" in res_no_auth.json()

    # 2. Com token inválido / corrompido
    res_invalid_token = await async_client.post(
        "/api/v1/job-hunter/hunt",
        headers={"Authorization": "Bearer invalid_tampered_token_xyz"},
        json=sample_payload,
    )
    assert res_invalid_token.status_code == 401, (
        f"Esperava 401 para token inválido, obteve: {res_invalid_token.status_code}"
    )

    # 3. Confirma que nenhum registro foi gerado no banco de dados
    apps_count = await db_session.execute(select(Application))
    assert len(apps_count.scalars().all()) == 0, (
        "Registros de Application foram indevidamente criados!"
    )

    notifs_count = await db_session.execute(select(Notification))
    assert len(notifs_count.scalars().all()) == 0, (
        "Registros de Notification foram indevidamente criados!"
    )
