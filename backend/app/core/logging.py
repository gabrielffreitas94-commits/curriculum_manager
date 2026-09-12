"""Sistema de Logging Estruturado (structlog) com conformidade Google Cloud Logging (GCP).

Implementa pipeline assíncrono de observabilidade com mascaramento automático de PII
e segredos (AppSec/LGPD), injeção de correlation_id via contextvars e formatação NDJSON.
"""

import logging
import re
import sys
from typing import Any

import structlog

from app.core.config import settings
from app.core.telemetry import get_correlation_id, get_user_id

# Chaves de atributos que devem ter seus valores automaticamente ofuscados
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "password",
        "hashed_password",
        "secret",
        "client_secret",
        "token",
        "id_token",
        "access_token",
        "refresh_token",
        "authorization",
        "bearer",
        "master_encryption_key",
        "gemini_api_key",
        "encrypted_api_key",
        "private_key",
        "credential",
        "supabase_key",
        "service_role_key",
        "database_url",
    }
)

# Padrões regex para detecção e ofuscação de credenciais em strings
GEMINI_KEY_PATTERN = re.compile(r"AIzaSy[A-Za-z0-9_-]{33}")
JWT_TOKEN_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
BEARER_AUTH_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE)

GCP_SEVERITY_MAP: dict[str, str] = {
    "debug": "DEBUG",
    "info": "INFO",
    "warning": "WARNING",
    "warn": "WARNING",
    "error": "ERROR",
    "critical": "CRITICAL",
    "fatal": "CRITICAL",
    "exception": "ERROR",
}


def _scrub_value(val: Any) -> Any:
    """Higieniza recursivamente valores em busca de segredos e credenciais."""
    if isinstance(val, str):
        masked = GEMINI_KEY_PATTERN.sub("[REDACTED_GEMINI_KEY]", val)
        masked = JWT_TOKEN_PATTERN.sub("[REDACTED_JWT]", masked)
        masked = BEARER_AUTH_PATTERN.sub("Bearer [REDACTED]", masked)
        return masked
    if isinstance(val, dict):
        return {
            k: (
                "[REDACTED]"
                if any(s in str(k).lower() for s in SENSITIVE_KEYS)
                else _scrub_value(v)
            )
            for k, v in val.items()
        }
    if isinstance(val, list | tuple | set):
        return [_scrub_value(item) for item in val]
    return val


def pii_and_secrets_scrubber(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processador de segurança que ofusca segredos e PII antes da emissão do log."""
    for key in list(event_dict.keys()):
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in SENSITIVE_KEYS):
            event_dict[key] = "[REDACTED]"
        else:
            event_dict[key] = _scrub_value(event_dict[key])
    return event_dict


def inject_telemetry_context(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Injeta automaticamente correlation_id e user_id a partir de contextvars."""
    corr_id = get_correlation_id()
    if corr_id and "correlation_id" not in event_dict:
        event_dict["correlation_id"] = corr_id

    uid = get_user_id()
    if uid and "user_id" not in event_dict:
        event_dict["user_id"] = uid

    return event_dict


def gcp_severity_processor(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processador de infraestrutura para compatibilidade com Google Cloud Logging.

    Mapeia a severidade para o padrão GCP ('severity') e sintetiza o objeto
    estruturado 'httpRequest' caso atributos neutros de requisição HTTP estejam presentes.
    """
    level = event_dict.get("level", "info").lower()
    event_dict["severity"] = GCP_SEVERITY_MAP.get(level, "DEFAULT")

    # Síntese do bloco nativo httpRequest do GCP a partir de atributos HTTP neutros (OTel)
    if "http_method" in event_dict and "status_code" in event_dict:
        duration_ms = event_dict.get("duration_ms", 0.0)
        url_val = event_dict.get("url") or event_dict.get("path", "")
        event_dict["httpRequest"] = {
            "requestMethod": event_dict["http_method"],
            "requestUrl": str(url_val),
            "status": event_dict["status_code"],
            "latency": f"{duration_ms / 1000:.4f}s",
            "userAgent": event_dict.get("user_agent", ""),
            "remoteIp": event_dict.get("remote_ip", ""),
        }

    return event_dict


def setup_logging() -> None:
    """Configura o pipeline de logging estruturado da aplicação."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        inject_telemetry_context,
        structlog.stdlib.add_log_level,
        gcp_severity_processor,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        pii_and_secrets_scrubber,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.LOG_FORMAT.lower() == "console" and settings.ENVIRONMENT == "development":
        final_renderer: Any = structlog.dev.ConsoleRenderer()
    else:
        final_renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [final_renderer],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    """Fábrica de loggers estruturados contextualizados.

    Args:
        name: Nome identificador do módulo ou componente.

    Returns:
        Instância do logger structlog vinculada ao componente.
    """
    logger = structlog.get_logger()
    if name:
        return logger.bind(logger_name=name)
    return logger
