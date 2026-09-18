"""Roteador Web do ThothCVs AI."""

from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["Web UI"])


@router.get("/", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def welcome_page(request: Request) -> HTMLResponse:
    """Renderiza a página inicial de boas-vindas com HTMX."""
    return templates.TemplateResponse(
        request=request,
        name="index.html.jinja2",
        context={"request": request},
    )
