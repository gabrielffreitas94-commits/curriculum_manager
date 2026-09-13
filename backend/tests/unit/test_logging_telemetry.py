"""Testes unitários para o módulo de logging estruturado e telemetria (OTel/GCP)."""

import pytest

from app.adapters.gcp_logging_adapter import gcp_cloud_logging_processor as gcp_severity_processor
from app.core.logging import (
    get_logger,
    inject_telemetry_context,
    pii_and_secrets_scrubber,
    setup_logging,
)
from app.core.telemetry import (
    clear_telemetry_context,
    get_correlation_id,
    get_user_id,
    set_correlation_id,
    set_user_id,
)


@pytest.fixture(autouse=True)
def clean_telemetry():
    """Garante isolamento do contexto assíncrono entre os testes."""
    clear_telemetry_context()
    yield
    clear_telemetry_context()


def test_telemetry_contextvars_lifecycle():
    """Valida o ciclo de vida completo de correlation_id e user_id nas contextvars."""
    assert get_correlation_id() is None
    assert get_user_id() is None

    set_correlation_id("test-corr-123")
    set_user_id("user-uuid-456")

    assert get_correlation_id() == "test-corr-123"
    assert get_user_id() == "user-uuid-456"

    clear_telemetry_context()
    assert get_correlation_id() is None
    assert get_user_id() is None


@pytest.mark.parametrize(
    "project_sensitive_key",
    [
        "api_key",
        "gemini_api_key",
        "encrypted_api_key",
        "master_encryption_key",
        "password",
        "hashed_password",
        "token",
        "id_token",
        "access_token",
        "refresh_token",
        "authorization",
        "client_secret",
        "private_key",
        "supabase_key",
        "service_role_key",
        "database_url",
    ],
)
def test_pii_scrubber_masks_all_project_sensitive_keys(project_sensitive_key: str):
    """Valida que todas as chaves sensíveis do projeto são estritamente ofuscadas no log.

    VETOR DE AMEAÇA:
    - OWASP A09:2021 — Security Logging and Monitoring Failures.
    - CWE-532: Insertion of Sensitive Information into Log File.
    - LGPD (Lei 13.709/2018) Art. 46: Vazamento de segredos e credenciais em logs de telemetria.
    - Impacto Potencial: Exposição inadvertida da chave mestre AES-GCM, chaves Gemini (BYOK),
      hashes de senhas ou tokens de sessão JWT a operadores de telemetria ou invasores com acesso
      aos agregadores de logs do Google Cloud.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Qualquer evento de log que contenha uma chave confidencial do sistema deve ter seu valor
      substituído incondicionalmente pela constante literal "[REDACTED]".

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - É terminantemente proibido afrouxar a lista SENSITIVE_KEYS ou assumir que certas chaves
      (ex: encrypted_api_key ou master_encryption_key) não precisam de sanitização por já estarem
      em base64 ou cifradas. A exposição de qualquer segredo estruturado viola o princípio da
      defesa em profundidade.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - O teste valida contra o oráculo imutável "[REDACTED]", rejeitando asserções tautológicas
      ou condicionais permissivas.
    """
    secret_value = "super-confidential-credential-xyz"
    event = {
        "event": "audit_probe",
        project_sensitive_key: secret_value,
    }

    scrubbed = pii_and_secrets_scrubber(None, "info", event)

    assert scrubbed[project_sensitive_key] == "[REDACTED]"
    assert secret_value not in str(scrubbed)


def test_pii_scrubber_masks_sensitive_keys():
    """Valida que atributos sensíveis têm seus valores ofuscados com [REDACTED].

    VETOR DE AMEAÇA:
    - OWASP A09:2021 — Security Logging and Monitoring Failures.
    - Impacto Potencial: Vazamento de tokens de autenticação e segredos de clientes em logs.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Atributos que contenham substrings confidenciais devem ser ofuscados para "[REDACTED]",
      mantendo apenas campos seguros inalterados.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Um refactor não deve utilizar regex permissivo que apenas substitua chaves completas
      ou falhe em chaves com prefixos/sufixos (ex: client_secret ou gemini_api_key).

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Asserção direta e literal contra o valor esperado de segurança "[REDACTED]".
    """
    event = {
        "event": "login_attempt",
        "api_key": "AIzaSySecretApiKey123456789012345678",
        "password": "SuperSecretPassword123!",
        "token": "some-secret-token",
        "gemini_api_key": "custom-key",
        "client_secret": "my-secret",
        "safe_field": "public_data",
    }

    scrubbed = pii_and_secrets_scrubber(None, "info", event)

    assert scrubbed["api_key"] == "[REDACTED]"
    assert scrubbed["password"] == "[REDACTED]"
    assert scrubbed["token"] == "[REDACTED]"
    assert scrubbed["gemini_api_key"] == "[REDACTED]"
    assert scrubbed["client_secret"] == "[REDACTED]"
    assert scrubbed["safe_field"] == "public_data"


def test_pii_scrubber_detects_patterns_in_values():
    """Valida detecção de padrões de chaves Gemini, JWT e Bearer em strings não mapeadas.

    VETOR DE AMEAÇA:
    - OWASP A09:2021 — Security Logging and Monitoring Failures.
    - Impacto Potencial: Vazamento acidental de tokens JWT e chaves Gemini inseridos em
      mensagens de erro ou dumps genéricos com chaves não listadas em SENSITIVE_KEYS.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Valores contendo padrões de chaves do Gemini ("AIzaSy...") devem ser ofuscados para
      "[REDACTED_GEMINI_KEY]", tokens JWT para "[REDACTED_JWT]" e cabeçalhos Bearer para
      "Bearer [REDACTED]", inclusive em estruturas aninhadas (dicionários e listas).

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Otimizações de desempenho prematuras que removam a varredura regex profunda em strings
      ou objetos aninhados reabrem vulnerabilidades de vazamento de chaves em traces de exceções.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Verificação de ausência absoluta da chave original e presença estrita dos marcadores de
      redação em todas as camadas da estrutura de dados.
    """
    gemini_key = "AIzaSyB12345678901234567890123456789012"
    jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThis"
    bearer_header = "Bearer some-long-token-value"

    event = {
        "event": "api_call_debug",
        "raw_message": f"Falha ao conectar usando {gemini_key} no endpoint",
        "auth_header": bearer_header,
        "dump_info": jwt_token,
        "nested": {
            "inner_key": gemini_key,
        },
        "items_list": [gemini_key, "safe"],
    }

    scrubbed = pii_and_secrets_scrubber(None, "debug", event)

    assert "[REDACTED_GEMINI_KEY]" in scrubbed["raw_message"]
    assert "AIzaSy" not in scrubbed["raw_message"]
    assert scrubbed["auth_header"] == "Bearer [REDACTED]"
    assert scrubbed["dump_info"] == "[REDACTED_JWT]"
    assert scrubbed["nested"]["inner_key"] == "[REDACTED_GEMINI_KEY]"
    assert scrubbed["items_list"][0] == "[REDACTED_GEMINI_KEY]"
    assert scrubbed["items_list"][1] == "safe"


def test_gcp_severity_processor_mapping():
    """Valida mapeamento de níveis do structlog para severity do Google Cloud Logging."""
    levels = [
        ("debug", "DEBUG"),
        ("info", "INFO"),
        ("warning", "WARNING"),
        ("warn", "WARNING"),
        ("error", "ERROR"),
        ("critical", "CRITICAL"),
        ("fatal", "CRITICAL"),
        ("unknown", "DEFAULT"),
    ]

    for lvl, expected_gcp_sev in levels:
        event = {"event": "test", "level": lvl}
        res = gcp_severity_processor(None, lvl, event)
        assert res["severity"] == expected_gcp_sev


def test_inject_telemetry_context_adds_contextvars():
    """Valida que correlation_id e user_id são injetados a partir das contextvars."""
    set_correlation_id("auto-corr-999")
    set_user_id("auto-user-888")

    event = {"event": "process_job"}
    res = inject_telemetry_context(None, "info", event)

    assert res["correlation_id"] == "auto-corr-999"
    assert res["user_id"] == "auto-user-888"


def test_inject_telemetry_context_preserves_existing():
    """Valida que correlation_id explícito não é sobrescrito pela contextvar."""
    set_correlation_id("ctx-corr-id")

    event = {"event": "custom", "correlation_id": "explicit-corr-id"}
    res = inject_telemetry_context(None, "info", event)

    assert res["correlation_id"] == "explicit-corr-id"


def test_setup_logging_and_get_logger():
    """Valida que o setup_logging configura o structlog e permite logar sem erros."""
    setup_logging()
    logger = get_logger("unit_test")
    assert logger is not None
    # Executa sem exceções
    logger.info("unit_test_log_event", status="ok", count=1)

    # Cobertura de get_logger sem argumento name
    unnamed_logger = get_logger()
    assert unnamed_logger is not None


def test_setup_logging_console_format(monkeypatch: pytest.MonkeyPatch):
    """Valida inicialização do structlog em modo console para desenvolvimento local."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "LOG_FORMAT", "console")
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    setup_logging()
    logger = get_logger("console_test")
    assert logger is not None

    # Restaura configuração padrão JSON
    monkeypatch.setattr(settings, "LOG_FORMAT", "json")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    setup_logging()


def test_gcp_cloud_logging_synthesizes_http_request():
    """Valida que o processador GCP sintetiza o bloco httpRequest a partir de campos neutros."""
    event = {
        "event": "http_request_finished",
        "level": "info",
        "http_method": "POST",
        "status_code": 201,
        "path": "/api/v1/resumes",
        "duration_ms": 150.5,
        "user_agent": "Mozilla/5.0",
        "remote_ip": "192.168.1.1",
    }

    processed = gcp_severity_processor(None, "info", event)

    assert processed["severity"] == "INFO"
    assert "httpRequest" in processed
    http_req = processed["httpRequest"]
    assert http_req["requestMethod"] == "POST"
    assert http_req["requestUrl"] == "/api/v1/resumes"
    assert http_req["status"] == 201
    assert http_req["latency"] == "0.1505s"
    assert http_req["userAgent"] == "Mozilla/5.0"
    assert http_req["remoteIp"] == "192.168.1.1"


def test_gcp_cloud_logging_without_http_method():
    """Valida que o processador GCP não sintetiza httpRequest quando ausente atributos HTTP."""
    event = {
        "event": "background_task",
        "level": "info",
    }

    processed = gcp_severity_processor(None, "info", event)
    assert processed["severity"] == "INFO"
    assert "httpRequest" not in processed


@pytest.mark.asyncio
async def test_guardrail_correlation_context_isolation_across_async_contexts():
    """Valida que o contexto de telemetria é estritamente isolado entre tarefas assíncronas.

    VETOR DE AMEAÇA:
    - OWASP A01:2021 — Broken Access Control / Cross-Tenant Data Leakage in Logs.
    - CWE-200: Exposure of Sensitive Information to an Unauthorized Actor.
    - Impacto Potencial: Vazamento de Correlation ID de um usuário para requisições de outros
      usuários em servidores ASGI assíncronos que reutilizam threads/event-loops, comprometendo
      a rastreabilidade e a conformidade com a LGPD em auditorias forenses.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Cada tarefa assíncrona ou ciclo de requisição deve ter suas ContextVars estritamente isoladas.
      A limpeza via clear_telemetry_context() deve garantir que nenhuma tarefa subsequente herde
      identificadores de sessões anteriores.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - É terminantemente proibido utilizar variáveis globais comuns ou singletons mutáveis em vez
      de contextvars.ContextVar para armazenar o correlation_id e user_id.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - O teste valida que após clear_telemetry_context(), get_correlation_id()
      retorna incondicionalmente None.
    """
    import asyncio

    async def task_a():
        set_correlation_id("corr-tenant-alpha")
        set_user_id("user-tenant-alpha")
        await asyncio.sleep(0.01)
        assert get_correlation_id() == "corr-tenant-alpha"
        assert get_user_id() == "user-tenant-alpha"
        clear_telemetry_context()
        assert get_correlation_id() is None
        assert get_user_id() is None

    async def task_b():
        await asyncio.sleep(0.005)
        # Contexto independente não deve enxergar tenant alpha
        assert get_correlation_id() is None
        assert get_user_id() is None
        set_correlation_id("corr-tenant-beta")
        await asyncio.sleep(0.01)
        assert get_correlation_id() == "corr-tenant-beta"
        clear_telemetry_context()

    await asyncio.gather(task_a(), task_b())
    assert get_correlation_id() is None
    assert get_user_id() is None


def test_guardrail_pii_scrubber_case_insensitivity_and_structure_resilience():
    """Valida que a sanitização de PII funciona de forma estrita sem distinção de
    maiúsculas/minúsculas.

    VETOR DE AMEAÇA:
    - OWASP A09:2021 — Security Logging and Monitoring Failures.
    - CWE-532: Insertion of Sensitive Information into Log File.
    - Impacto Potencial: Vazamento de segredos em chaves com capitalização mista ou não usual
      (ex: 'pAsSwOrD', 'AUTHORIZATION', 'Api_Key') em logs de produção.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O scrubber de PII deve realizar o matching case-insensitive de chaves e ocultar os valores
      incondicionalmente para "[REDACTED]".

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - É terminantemente proibido depender de comparações estritas de strings com distinção entre
      maiúsculas e minúsculas ao auditar chaves confidenciais.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Toda chave confidencial em qualquer variação de caixa deve ter seu valor estritamente
      substituído pela constante "[REDACTED]".
    """
    event = {
        "event": "probe_security",
        "pAsSwOrD": "PlainSecret123",
        "AUTHORIZATION": "Bearer token123",
        "Api_Key": "AIzaSyCustomKey",
        "nested": {
            "SECRET": "deepSecret",
            "TOKEN": "deepToken",
        },
    }

    scrubbed = pii_and_secrets_scrubber(None, "info", event)

    assert scrubbed["pAsSwOrD"] == "[REDACTED]"
    assert scrubbed["AUTHORIZATION"] == "[REDACTED]"
    assert scrubbed["Api_Key"] == "[REDACTED]"
    assert scrubbed["nested"]["SECRET"] == "[REDACTED]"
    assert scrubbed["nested"]["TOKEN"] == "[REDACTED]"
