"""Roteador Web do ThothCVs AI para renderização de páginas e fragmentos via HTMX e Jinja2.

Fornece a interface visual servida diretamente pelo FastAPI sem dependência de Node.js,
aproveitando reatividade atômica via HTMX e templates Jinja2.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings

# Diretório canônico de templates HTML
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["Web UI"])


@router.get("/", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def welcome_page(request: Request) -> HTMLResponse:
    """Renderiza a página inicial de boas-vindas do ThothCVs AI.

    Args:
        request: Objeto da requisição HTTP ASGI.

    Returns:
        HTMLResponse: Documento HTML completo renderizado com base no template Jinja2.
    """
    return templates.TemplateResponse(
        request=request,
        name="welcome.html.jinja2",
        context={"request": request},
    )


@router.get("/htmx/ping", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def htmx_ping(request: Request) -> HTMLResponse:
    """Endpoint de demonstração e teste de reatividade assíncrona do HTMX.

    Retorna um fragmento HTML parcial destinado a substituição atômica no DOM.

    Args:
        request: Objeto da requisição HTTP ASGI.

    Returns:
        HTMLResponse: Fragmento HTML de resposta.
    """
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return templates.TemplateResponse(
        request=request,
        name="partials/ping_response.html.jinja2",
        context={
            "request": request,
            "status": "healthy",
            "version": settings.VERSION,
            "timestamp": now_utc,
        },
    )
