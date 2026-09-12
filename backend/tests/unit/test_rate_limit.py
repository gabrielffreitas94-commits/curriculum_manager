"""Testes unitários para o módulo core/rate_limit.py."""

from unittest.mock import MagicMock

from fastapi import Request, status
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter, rate_limit_exceeded_handler


def test_limiter_instance_and_key_func() -> None:
    """Valida que o Limiter está inicializado e sua key_func extrai o IP do cliente."""
    assert limiter is not None
    assert callable(limiter._key_func)

    mock_request = MagicMock(spec=Request)
    mock_request.client = MagicMock()
    mock_request.client.host = "192.168.1.100"

    assert limiter._key_func(mock_request) == "192.168.1.100"


def test_limiter_key_func_fallback_when_client_is_none() -> None:
    """Valida o fallback para '127.0.0.1' quando o socket do cliente não possui host."""
    mock_request = MagicMock(spec=Request)
    mock_request.client = None

    assert limiter._key_func(mock_request) == "127.0.0.1"


def test_rate_limit_exceeded_handler_returns_429_with_headers() -> None:
    """Garante que exceções RateLimitExceeded retornem status HTTP 429 e cabeçalho Retry-After.

    VETOR DE AMEAÇA:
    - OWASP A04:2021 (Insecure Design) / CWE-799 (Improper Control of Interaction Frequency)
      e CWE-400 (Uncontrolled Resource Consumption / DoS).
    - Impacto: Sem retorno 429 padronizado e Retry-After, clientes automatizados não sabem
      quando cessar rajadas, perpetuando consumo de recursos e custos de IA.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O handler DEVE interceptar RateLimitExceeded e responder com status 429,
      cabeçalho Retry-After: 60 e JSON explicativo com detalhe do limite atingido.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Um refactor que altere o status code para 500 ocultaria o esgotamento de taxa
      como falha interna da aplicação, mascarando abusos e alarmes de infraestrutura.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Assere que a resposta tem status_code == 429, header 'Retry-After' == '60'
      e chaves 'detail' e 'error' presentes no corpo.
    """
    mock_request = MagicMock(spec=Request)
    mock_limit = MagicMock()
    mock_limit.error_message = None
    mock_limit.limit = "5 per 1 minute"
    exc = RateLimitExceeded(mock_limit)

    response = rate_limit_exceeded_handler(mock_request, exc)

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.headers.get("Retry-After") == "60"

    import json

    body = json.loads(response.body.decode("utf-8"))
    assert "Limite de requisições excedido: 5 per 1 minute" in body["detail"]
    assert body["error"] == "Rate limit exceeded: 5 per 1 minute"
