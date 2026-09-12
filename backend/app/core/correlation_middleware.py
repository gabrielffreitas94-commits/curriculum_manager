"""Middleware HTTP de Correlação e Rastreabilidade Distribuída.

Extrai ou gera o cabeçalho X-Correlation-ID, amarra aos contextvars assíncronos
e registra o ciclo de vida completo da requisição com latência e telemetria GCP.
"""

import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger
from app.core.telemetry import clear_telemetry_context, set_correlation_id

logger = get_logger("http_middleware")


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware ASGI para propagação de Correlation ID e registro HTTP no Cloud Logging."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Processa a requisição HTTP injetando o identificador de correlação.

        Args:
            request: Requisição HTTP recebida.
            call_next: Próximo handler no pipeline do FastAPI.

        Returns:
            Response: Resposta HTTP com cabeçalho X-Correlation-ID adicionado.
        """
        # Extrai ou gera identificador único de correlação (UUIDv4)
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id or not correlation_id.strip():
            correlation_id = str(uuid.uuid4())
        else:
            correlation_id = correlation_id.strip()

        set_correlation_id(correlation_id)
        start_time = time.perf_counter()

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "http_request_unhandled_exception",
                http_method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                error=str(exc),
                exc_info=True,
            )
            clear_telemetry_context()
            raise

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Correlation-ID"] = correlation_id

        # Emissão de log proporcional à criticidade do status HTTP (campos neutros OTel)
        log_kwargs: dict[str, Any] = {
            "http_method": request.method,
            "path": request.url.path,
            "url": str(request.url),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "user_agent": request.headers.get("user-agent", ""),
            "remote_ip": request.client.host if request.client else "",
        }

        if response.status_code >= 500:
            logger.error("http_request_finished", **log_kwargs)
        elif response.status_code >= 400:
            logger.warning("http_request_finished", **log_kwargs)
        else:
            logger.info("http_request_finished", **log_kwargs)

        clear_telemetry_context()
        return response
