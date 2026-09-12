"""Middleware de Cabeçalhos de Segurança HTTP para o ThothCVs AI Backend.

Implementa defesa em profundidade (Defense-in-Depth) conforme as diretrizes do
OWASP Top 10 (A05:2021 - Security Misconfiguration) e STRIDE, mitigando ataques de
MIME Sniffing, Clickjacking, vazamento de credenciais via Referer e exigindo conexões
estritamente criptografadas (HSTS) em ambiente produtivo.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware HTTP para injeção automática de cabeçalhos de segurança em todas as respostas."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Processa a requisição e anexa cabeçalhos de segurança à resposta.

        Args:
            request: Requisição HTTP recebida.
            call_next: Próximo handler na cadeia de execução ASGI.

        Returns:
            Response: Resposta HTTP com cabeçalhos de segurança anexados.
        """
        response = await call_next(request)

        # 1. Bloqueio de MIME-sniffing (CWE-430)
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 2. Prevenção contra Clickjacking e inserção em iframes maliciosos (CWE-1021)
        response.headers["X-Frame-Options"] = "DENY"

        # 3. Política estrita de Referrer para impedir vazamento de URLs internas (CWE-200)
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 4. Restrição de permissões de hardware/dispositivos pelo navegador
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        # 5. Content Security Policy (CSP) e HTTP Strict Transport Security (HSTS)
        if settings.ENVIRONMENT == "production":
            hsts_val = f"max-age={settings.HSTS_MAX_AGE_SECONDS}"
            if settings.HSTS_INCLUDE_SUBDOMAINS:
                hsts_val += "; includeSubDomains"
            if settings.HSTS_PRELOAD:
                hsts_val += "; preload"

            response.headers["Strict-Transport-Security"] = hsts_val
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
            )
        else:
            response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"

        return response
