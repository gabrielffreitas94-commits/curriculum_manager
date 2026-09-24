"""Roteador Web do ThothCVs AI (Driving Adapter)."""

import hmac
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.v1.deps import get_auth_service, google_oauth_adapter
from app.core.config import settings
from app.core.logging import get_logger
from app.core.telemetry import set_user_id
from app.domain.models import User
from app.ports.oauth_port import OAuthError
from app.services.auth_service import AuthService

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

logger = get_logger("web_router")

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
    user = await auth_service.get_authenticated_user(token)
    if user is not None:
        set_user_id(str(user.id))
    return user


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
    """Redireciona o navegador do usuário para o endpoint de autorização do Google com state."""
    state = secrets.token_urlsafe(32)
    auth_url = google_oauth_adapter.get_authorization_url(state=state)
    logger.info("oauth_login_redirect_initiated", provider="google")
    response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=(settings.ENVIRONMENT in ("production", "staging")),
        samesite="lax",
        max_age=300,
        path="/auth/callback/google",
    )
    return response


@router.get("/auth/callback/google")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Processa o callback de autorização do Google OAuth 2.0 e autentica o usuário."""
    if error or not code:
        logger.warning(
            "oauth_callback_access_denied",
            provider="google",
            error=str(error) if error else "missing_code",
        )
        response = RedirectResponse(
            url="/?auth_error=google_denied", status_code=status.HTTP_302_FOUND
        )
        response.delete_cookie(key="oauth_state", path="/auth/callback/google")
        return response

    expected_state = request.cookies.get("oauth_state")
    if not state or not expected_state or not hmac.compare_digest(state, expected_state):
        logger.warning(
            "oauth_csrf_state_mismatch",
            provider="google",
            has_state=bool(state),
            has_cookie=bool(expected_state),
        )
        response = RedirectResponse(
            url="/?auth_error=csrf_detected", status_code=status.HTTP_302_FOUND
        )
        response.delete_cookie(key="oauth_state", path="/auth/callback/google")
        return response

    try:
        user, session_token = await auth_service.authenticate_oauth_user(
            oauth_port=google_oauth_adapter, code=code
        )
    except OAuthError as exc:
        logger.error(
            "oauth_callback_failed",
            provider="google",
            error=str(exc),
            exc_info=True,
        )
        response = RedirectResponse(
            url="/?auth_error=oauth_failed", status_code=status.HTTP_302_FOUND
        )
        response.delete_cookie(key="oauth_state", path="/auth/callback/google")
        return response

    logger.info(
        "oauth_callback_success",
        provider="google",
        user_id=str(user.id),
    )
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response=response, session_token=session_token)
    response.delete_cookie(key="oauth_state", path="/auth/callback/google")
    return response


@router.post("/auth/logout", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def logout(request: Request) -> Response:
    """Encerra a sessão Web do usuário removendo o cookie session_token."""
    logger.info("web_user_logged_out")
    response = HTMLResponse(content="", status_code=status.HTTP_200_OK)
    response.delete_cookie(key="session_token", path="/")
    response.headers["HX-Refresh"] = "true"
    return response
