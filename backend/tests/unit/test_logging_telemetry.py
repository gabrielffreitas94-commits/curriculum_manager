"""Testes unitários para o módulo de logging estruturado e telemetria (OTel/GCP)."""

import pytest

from app.core.logging import (
    gcp_severity_processor,
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


def test_pii_scrubber_masks_sensitive_keys():
    """Valida que atributos sensíveis têm seus valores ofuscados com [REDACTED]."""
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
    """Valida detecção de padrões de chaves Gemini, JWT e Bearer em strings não mapeadas."""
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
