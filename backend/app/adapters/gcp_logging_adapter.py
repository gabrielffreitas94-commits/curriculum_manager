"""Adaptador de infraestrutura para Google Cloud Logging (Hexagonal Architecture).

Converte eventos de log estruturados em formato nativo do Google Cloud Run (GCP),
mapeando a severidade para o campo 'severity' e sintetizando o objeto 'httpRequest'
para correlação automática no Cloud Logging e Cloud Trace.
"""

from typing import Any

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


def gcp_cloud_logging_processor(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processador de infraestrutura que adapta o log estruturado para o Google Cloud Logging.

    Args:
        logger: Instância do logger ativa.
        method_name: Nome do método de log invocado ('info', 'error', etc.).
        event_dict: Dicionário contendo os atributos do evento.

    Returns:
        dict[str, Any]: Evento enriquecido com atributos 'severity' e 'httpRequest' do GCP.
    """
    level = event_dict.get("level", "info").lower()
    event_dict["severity"] = GCP_SEVERITY_MAP.get(level, "DEFAULT")

    # Síntese do bloco nativo httpRequest do GCP para agregação no Cloud Run
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
