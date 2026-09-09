"""Ponto de entrada da aplicação FastAPI do ThothCVs AI Backend.

Configura middlewares de segurança, CORS, gerenciamento de ciclo de vida (lifespan)
e registra os roteadores da versão 1 da API.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.applications import router as applications_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.profile import router as profile_router
from app.api.v1.resumes import router as resumes_router
from app.api.v1.users import router as users_router
from app.core.config import settings


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
    yield
    # Rotinas de encerramento (shutdown)


def create_application() -> FastAPI:
    """Fábrica de inicialização e configuração da aplicação FastAPI.

    Returns:
        FastAPI: Instância totalmente configurada pronta para execução.
    """
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="API de Gestão Inteligente de Currículos e ATS Pessoal com IA",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
        lifespan=lifespan,
    )

    # Configuração de CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registro de rotas de diagnóstico globais (Cloud Run)
    application.include_router(health_router)

    # Registro de rotas versionadas sob /api/v1
    application.include_router(health_router, prefix=settings.API_V1_STR)
    application.include_router(auth_router, prefix=settings.API_V1_STR)
    application.include_router(users_router, prefix=settings.API_V1_STR)
    application.include_router(profile_router, prefix=settings.API_V1_STR)
    application.include_router(resumes_router, prefix=settings.API_V1_STR)
    application.include_router(applications_router, prefix=settings.API_V1_STR)

    return application


app = create_application()
