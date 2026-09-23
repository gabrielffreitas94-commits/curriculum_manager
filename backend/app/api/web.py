"""Roteador Web do ThothCVs AI (Driving Adapter)."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.v1.deps import get_auth_service, google_oauth_adapter
from app.core.config import settings
from app.domain.models import User
from app.ports.oauth_port import OAuthError
from app.services.auth_service import AuthService

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["Web UI"])


def _set_session_cookie(response: Response, session_token: str) -> None:
    """Configura o cookie HTTP-only com proteções estritas de transporte e CSRF."""
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=(settings.ENVIRONMENT in ("production", "staging")),
        samesite="lax",
        max_age=86400 * 7,
        path="/",
    )


async def get_authenticated_web_user(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> User | None:
    """Recupera o usuário autenticado na sessão Web a partir do Cookie session_token."""
    token = request.cookies.get("session_token")
    return await auth_service.get_authenticated_user(token)


@router.get("/", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def welcome_page(
    request: Request,
    current_user: User | None = Depends(get_authenticated_web_user),
) -> HTMLResponse:
    """Renderiza a página inicial de boas-vindas com HTMX e estado de autenticação."""
    return templates.TemplateResponse(
        request=request,
        name="index.html.jinja2",
        context={"request": request, "current_user": current_user},
    )


@router.get("/auth/modal", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def login_modal(request: Request) -> HTMLResponse:
    """Renderiza o fragmento do modal de login com Google, LinkedIn e E-mail/Senha."""
    return templates.TemplateResponse(
        request=request,
        name="login_modal.html.jinja2",
        context={"request": request},
    )


@router.get("/auth/login/google", status_code=status.HTTP_302_FOUND)
async def login_google_redirect() -> Response:
    """Redireciona o navegador do usuário para o endpoint de autorização do Google."""
    auth_url = google_oauth_adapter.get_authorization_url()
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/auth/callback/google")
async def google_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Processa o callback de autorização do Google OAuth 2.0 e autentica o usuário."""
    if error or not code:
        return RedirectResponse(url="/?auth_error=google_denied", status_code=status.HTTP_302_FOUND)

    try:
        _, session_token = await auth_service.authenticate_oauth_user(
            oauth_port=google_oauth_adapter, code=code
        )
    except OAuthError:
        return RedirectResponse(url="/?auth_error=oauth_failed", status_code=status.HTTP_302_FOUND)

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response=response, session_token=session_token)
    return response


@router.post("/auth/login/google", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def login_google(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Realiza autenticação via conta Google (fallback / mock de desenvolvimento)."""
    _, token_val = await auth_service.authenticate_mock_user(
        mock_identifier="mock_google_user",
        email="usuario.google@exemplo.com",
        full_name="Usuário Google",
    )
    response = HTMLResponse(content="", status_code=status.HTTP_200_OK)
    _set_session_cookie(response=response, session_token=token_val)
    response.headers["HX-Refresh"] = "true"
    return response


@router.post("/auth/login/linkedin", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def login_linkedin(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Realiza autenticação via conta LinkedIn (fallback / mock de desenvolvimento)."""
    _, token_val = await auth_service.authenticate_mock_user(
        mock_identifier="mock_linkedin_user",
        email="usuario.linkedin@exemplo.com",
        full_name="Usuário LinkedIn",
    )
    response = HTMLResponse(content="", status_code=status.HTTP_200_OK)
    _set_session_cookie(response=response, session_token=token_val)
    response.headers["HX-Refresh"] = "true"
    return response


@router.post("/auth/logout", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def logout(request: Request) -> Response:
    """Encerra a sessão Web do usuário removendo o cookie session_token."""
    response = HTMLResponse(content="", status_code=status.HTTP_200_OK)
    response.delete_cookie(key="session_token", path="/")
    response.headers["HX-Refresh"] = "true"
    return response
