"""Ponto de entrada da aplicação FastAPI do ThothCVs AI Backend.

Configura middlewares de segurança, CORS, gerenciamento de ciclo de vida (lifespan)
e registra os roteadores da versão 1 da API.
"""

import html
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.adapters.gcp_logging_adapter import gcp_cloud_logging_processor
from app.api.v1.applications import router as applications_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.job_hunter import router as job_hunter_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.profile import router as profile_router
from app.api.v1.resumes import router as resumes_router
from app.api.v1.users import router as users_router
from app.api.web import router as web_router
from app.core.config import settings
from app.core.correlation_middleware import CorrelationMiddleware
from app.core.logging import get_logger, setup_logging
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.security_headers import SecurityHeadersMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerenciador de ciclo de vida assíncrono da aplicação.

    Executa rotinas de aquecimento e encerramento de conexões
    durante o startup e shutdown do servidor Uvicorn.

    Args:
        app: Instância ativa do FastAPI.

    Yields:
        None: Contexto de execução enquanto a aplicação permanece ativa.
    """
    # Rotinas de inicialização (startup)
    setup_logging(cloud_processor=gcp_cloud_logging_processor)
    yield
    # Rotinas de encerramento (shutdown)


def create_application() -> FastAPI:
    """Fábrica de inicialização e configuração da aplicação FastAPI.

    Returns:
        FastAPI: Instância totalmente configurada pronta para execução.
    """
    setup_logging(cloud_processor=gcp_cloud_logging_processor)

    openapi_url = (
        f"{settings.API_V1_STR}/openapi.json" if settings.ENVIRONMENT != "production" else None
    )
    docs_url = f"{settings.API_V1_STR}/docs" if settings.ENVIRONMENT != "production" else None
    redoc_url = f"{settings.API_V1_STR}/redoc" if settings.ENVIRONMENT != "production" else None

    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="API de Gestão Inteligente de Currículos e ATS Pessoal com IA",
        openapi_url=openapi_url,
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )

    # Middleware de Correlação e Rastreabilidade Distribuída (OTel / GCP)
    application.add_middleware(CorrelationMiddleware)

    # Configuração de CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Configuração de Cabeçalhos de Segurança HTTP (Defense-in-Depth)
    if settings.SECURITY_HEADERS_ENABLED:
        application.add_middleware(SecurityHeadersMiddleware)

    # Configuração de Rate Limiting (SlowAPI)
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]
    application.add_middleware(SlowAPIMiddleware)

    # Guardrails Globais de Sanitização de Exceções e Anti-Vazamento (CWE-209 / OWASP A05)
    @application.exception_handler(StarletteHTTPException)
    async def global_http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        """Sanitiza exceções HTTP impedindo vazamento de erros 5xx para usuários."""
        if exc.status_code >= 500:
            logger.error(
                "http_server_error_sanitized",
                status_code=exc.status_code,
                path=request.url.path,
                method=request.method,
                error=str(exc.detail),
                exc_info=True,
            )
            safe_message = (
                "Ocorreu um erro interno no servidor. Por favor, tente novamente mais tarde."
            )
            is_html = "text/html" in request.headers.get(
                "accept", ""
            ) and not request.url.path.startswith(settings.API_V1_STR)
            if is_html:
                return HTMLResponse(
                    content=(
                        '<div class="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/60 '
                        "border border-rose-200 dark:border-rose-900 text-rose-700 "
                        'dark:text-rose-300 text-sm font-medium space-y-1">'
                        f"<strong>⚠️ Erro ({exc.status_code}):</strong> "
                        f"<span>{safe_message}</span></div>"
                    ),
                    status_code=exc.status_code,
                )
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": safe_message},
                headers=exc.headers,
            )

        is_html_client = "text/html" in request.headers.get(
            "accept", ""
        ) and not request.url.path.startswith(settings.API_V1_STR)
        if is_html_client:
            escaped_detail = html.escape(str(exc.detail))
            return HTMLResponse(
                content=(
                    '<div class="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/60 '
                    "border border-amber-200 dark:border-amber-900 text-amber-700 "
                    'dark:text-amber-300 text-sm font-medium space-y-1">'
                    f"<strong>⚠️ Aviso:</strong> <span>{escaped_detail}</span></div>"
                ),
                status_code=exc.status_code,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    @application.exception_handler(Exception)
    async def global_unhandled_exception_handler(request: Request, exc: Exception) -> Response:
        """Intercepta exceções não tratadas garantindo fail-closed contra CWE-209."""
        logger.error(
            "unhandled_server_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        safe_message = "Ocorreu um erro interno no servidor. Por favor, tente novamente mais tarde."
        is_html = "text/html" in request.headers.get(
            "accept", ""
        ) and not request.url.path.startswith(settings.API_V1_STR)
        if is_html:
            return HTMLResponse(
                content=(
                    '<div class="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/60 '
                    "border border-rose-200 dark:border-rose-900 text-rose-700 "
                    'dark:text-rose-300 text-sm font-medium space-y-1">'
                    f"<strong>⚠️ Erro Interno:</strong> <span>{safe_message}</span></div>"
                ),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": safe_message},
        )

    # Montagem de arquivos estáticos (HTMX, CSS, assets)
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Registro de rotas web (Interface HTMX)
    application.include_router(web_router)

    # Registro de rotas de diagnóstico globais (Cloud Run)
    application.include_router(health_router)

    # Registro de rotas versionadas sob /api/v1
    application.include_router(health_router, prefix=settings.API_V1_STR)
    application.include_router(auth_router, prefix=settings.API_V1_STR)
    application.include_router(users_router, prefix=settings.API_V1_STR)
    application.include_router(profile_router, prefix=settings.API_V1_STR)
    application.include_router(resumes_router, prefix=settings.API_V1_STR)
    application.include_router(applications_router, prefix=settings.API_V1_STR)
    application.include_router(notifications_router, prefix=settings.API_V1_STR)
    application.include_router(job_hunter_router, prefix=settings.API_V1_STR)

    return application


app = create_application()
