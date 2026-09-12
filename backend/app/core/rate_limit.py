"""Módulo de controle de taxa de requisições (Rate Limiting) com SlowAPI.

Protege endpoints sensíveis e com processamento intensivo de IA (Gemini) contra
ataques de negação de serviço (DoS) e esgotamento financeiro de cotas de API.
"""

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

limiter: Limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.RATE_LIMIT_ENABLED,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Manipulador customizado para exceções de cota de requisições excedida (HTTP 429).

    Garante que o cliente receba uma mensagem estruturada e o cabeçalho Retry-After
    conforme as boas práticas da RFC 6585.

    Args:
        request: Requisição HTTP interceptada.
        exc: Exceção RateLimitExceeded contendo detalhes da regra violada.

    Returns:
        JSONResponse com status 429, payload informativo e cabeçalho Retry-After.
    """
    retry_after = "60"
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": f"Limite de requisições excedido: {exc.detail}. Tente novamente mais tarde.",
            "error": f"Rate limit exceeded: {exc.detail}",
        },
        headers={"Retry-After": retry_after},
    )
