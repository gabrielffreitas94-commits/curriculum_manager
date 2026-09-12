"""Ponto de entrada da aplicação FastAPI do ThothCVs AI Backend.

Configura middlewares de segurança, CORS, gerenciamento de ciclo de vida (lifespan)
e registra os roteadores da versão 1 da API.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.adapters.gcp_logging_adapter import gcp_cloud_logging_processor
from app.api.v1.applications import router as applications_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.profile import router as profile_router
from app.api.v1.resumes import router as resumes_router
from app.api.v1.users import router as users_router
from app.core.config import settings
from app.core.correlation_middleware import CorrelationMiddleware
from app.core.logging import setup_logging
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.security_headers import SecurityHeadersMiddleware


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

    return application


app = create_application()
