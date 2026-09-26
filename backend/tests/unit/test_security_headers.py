"""Testes unitários para cabeçalhos de segurança HTTP e restrição de documentação OpenAPI/Swagger.

Valida a conformidade contra OWASP Top 10 (A05:2021 - Security Misconfiguration)
e assegura isolamento em ambientes de produção.
"""

import base64

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_application


@pytest.mark.asyncio
async def test_security_headers_in_development(async_client: AsyncClient) -> None:
    """
    VETOR DE AMEAÇA:
    MIME Sniffing (CWE-430), Clickjacking (CWE-1021) e
    vazamento de rotas/tokens via Referer (CWE-200).

    COMPORTAMENTO ESPERADO:
    Todas as respostas HTTP devem conter os cabeçalhos X-Content-Type-Options: nosniff,
    X-Frame-Options: DENY, Referrer-Policy e Permissions-Policy restritivas.

    PREMISSA DO GUARDRAIL:
    Em ambiente de desenvolvimento, a CSP restringe frame-ancestors e não força HSTS para
    não quebrar servidores locais HTTP.

    ORIENTAÇÃO PARA AGENTES IA:
    Não remova nem relaxe os cabeçalhos de segurança na SecurityHeadersMiddleware.
    """
    response = await async_client.get("/healthz")
    assert response.status_code == 200

    headers = response.headers
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in headers.get("permissions-policy", "")
    assert "microphone=()" in headers.get("permissions-policy", "")
    assert "geolocation=()" in headers.get("permissions-policy", "")
    assert headers.get("content-security-policy") == "frame-ancestors 'none'"
    assert "strict-transport-security" not in headers


@pytest.mark.asyncio
async def test_security_headers_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    VETOR DE AMEAÇA:
    Comunicação não-HTTPS permitindo Man-in-the-Middle (CWE-319) e injeção de scripts (CWE-79).

    COMPORTAMENTO ESPERADO:
    Em ambiente 'production', a aplicação deve impor HSTS (Strict-Transport-Security) com
    max-age de pelo menos 1 ano e subdomínios, além de CSP estrita 'default-src none'.

    PREMISSA DO GUARDRAIL:
    Assegurar que settings.ENVIRONMENT == 'production' ativa imediatamente a
    blindagem HSTS e CSP estrita.

    ORIENTAÇÃO PARA AGENTES IA:
    Não desative HSTS nem relaxe Content-Security-Policy em produção.
    """
    valid_prod_key = base64.b64encode(b"P" * 32).decode()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", valid_prod_key)

    import app.core.config
    import app.core.security_headers
    import app.main

    prod_settings = Settings(ENVIRONMENT="production", MASTER_ENCRYPTION_KEY=valid_prod_key)
    monkeypatch.setattr(app.core.config, "settings", prod_settings)
    monkeypatch.setattr(app.core.security_headers, "settings", prod_settings)
    monkeypatch.setattr(app.main, "settings", prod_settings)

    prod_app = create_application()
    transport = ASGITransport(app=prod_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200

        headers = response.headers
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("x-frame-options") == "DENY"
        assert headers.get("strict-transport-security") == "max-age=31536000; includeSubDomains"
        assert headers.get("content-security-policy") == (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'"
        )


@pytest.mark.asyncio
async def test_hsts_variations_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Testa ramificações de HSTS sem includeSubDomains e com preload ativo."""
    valid_prod_key = base64.b64encode(b"P" * 32).decode()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", valid_prod_key)

    import app.core.config
    import app.core.security_headers
    import app.main

    custom_settings = Settings(
        ENVIRONMENT="production",
        MASTER_ENCRYPTION_KEY=valid_prod_key,
        HSTS_INCLUDE_SUBDOMAINS=False,
        HSTS_PRELOAD=True,
    )
    monkeypatch.setattr(app.core.config, "settings", custom_settings)
    monkeypatch.setattr(app.core.security_headers, "settings", custom_settings)
    monkeypatch.setattr(app.main, "settings", custom_settings)

    app_instance = create_application()
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.headers.get("strict-transport-security") == "max-age=31536000; preload"


@pytest.mark.asyncio
async def test_swagger_docs_enabled_in_development(async_client: AsyncClient) -> None:
    """Verifica se OpenAPI JSON e Swagger Docs estão disponíveis em desenvolvimento."""
    docs_resp = await async_client.get("/api/v1/docs")
    assert docs_resp.status_code == 200

    openapi_resp = await async_client.get("/api/v1/openapi.json")
    assert openapi_resp.status_code == 200
    assert "openapi" in openapi_resp.json()


@pytest.mark.asyncio
async def test_swagger_docs_disabled_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    VETOR DE AMEAÇA:
    Reconhecimento e enumeração de superfície de ataque via Swagger/OpenAPI em produção (OWASP A05).

    COMPORTAMENTO ESPERADO:
    Em produção, /docs, /redoc e /openapi.json devem retornar 404 Not Found.

    PREMISSA DO GUARDRAIL:
    Assegura que a fábrica de inicialização desative openapi_url, docs_url e
    redoc_url quando ENVIRONMENT == 'production'.

    ORIENTAÇÃO PARA AGENTES IA:
    Nunca habilite Swagger ou OpenAPI schema em produção sem autenticação e autorização prévia.
    """
    valid_prod_key = base64.b64encode(b"P" * 32).decode()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", valid_prod_key)

    import app.core.config
    import app.main

    prod_settings = Settings(ENVIRONMENT="production", MASTER_ENCRYPTION_KEY=valid_prod_key)
    monkeypatch.setattr(app.core.config, "settings", prod_settings)
    monkeypatch.setattr(app.main, "settings", prod_settings)

    prod_app = create_application()
    transport = ASGITransport(app=prod_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        docs_resp = await client.get("/api/v1/docs")
        assert docs_resp.status_code == 404

        redoc_resp = await client.get("/api/v1/redoc")
        assert redoc_resp.status_code == 404

        openapi_resp = await client.get("/api/v1/openapi.json")
        assert openapi_resp.status_code == 404


@pytest.mark.asyncio
async def test_security_headers_disabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante cobertura de ramo quando SECURITY_HEADERS_ENABLED for falso."""
    import app.core.config
    import app.main

    disabled_settings = Settings(SECURITY_HEADERS_ENABLED=False)
    monkeypatch.setattr(app.core.config, "settings", disabled_settings)
    monkeypatch.setattr(app.main, "settings", disabled_settings)

    app_instance = create_application()
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        # Headers customizados não foram injetados
        assert "x-frame-options" not in response.headers
