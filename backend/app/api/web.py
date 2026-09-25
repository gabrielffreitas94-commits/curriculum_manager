"""Roteador Web do ThothCVs AI (Driving Adapter)."""

import hmac
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.v1.deps import (
    get_auth_service,
    get_profile_service,
    get_resume_parser_adapter,
    google_oauth_adapter,
    resolve_gemini_api_key,
)
from app.core.config import settings
from app.core.file_security import FileSecurityError, validate_resume_file
from app.core.logging import get_logger
from app.core.telemetry import set_user_id
from app.domain.models import User
from app.ports.oauth_port import OAuthError
from app.ports.resume_parser_port import ParsedProfileDTO, ResumeParserError
from app.services.auth_service import AuthService
from app.services.profile_service import ProfileService

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


# ==================== DOSSIÊ PROFISSIONAL (WEB UI) ====================
@router.get("/profile", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def profile_page(
    request: Request,
    current_user: User | None = Depends(get_authenticated_web_user),
    profile_service: ProfileService = Depends(get_profile_service),
) -> Response:
    """Renderiza a página principal do Dossiê Profissional com o repositório do candidato."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    dossier = await profile_service.get_full_dossier(current_user.id)
    return templates.TemplateResponse(
        request=request,
        name="profile/index.html.jinja2",
        context={
            "request": request,
            "current_user": current_user,
            "dossier": dossier,
            "active_tab": "profile",
        },
    )


@router.post("/profile/import-cv", response_class=HTMLResponse)
async def import_cv_upload(
    request: Request,
    file: UploadFile = File(...),
    current_user: User | None = Depends(get_authenticated_web_user),
) -> Response:
    """Processa o upload de um currículo (PDF/DOCX) e retorna o modal de revisão via HTMX."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    file_bytes = await file.read()
    try:
        mime_type, _ = validate_resume_file(
            file_bytes=file_bytes,
            filename=file.filename or "resume",
            content_type=file.content_type,
        )
    except FileSecurityError as exc:
        logger.warning("web_resume_upload_rejected", error=str(exc))
        modal_html = (
            '<div id="import-review-modal-backdrop" class="fixed inset-0 z-50 flex '
            'items-center justify-center p-4 bg-slate-950/60" role="dialog" aria-modal="true">\n'
            '  <div class="bg-white dark:bg-slate-900 rounded-2xl p-6 max-w-md w-full '
            'border border-rose-200 dark:border-rose-900 shadow-xl text-center space-y-4">\n'
            '    <div class="w-12 h-12 rounded-full bg-rose-100 text-rose-600 '
            "dark:bg-rose-950 dark:text-rose-400 mx-auto flex items-center justify-center "
            'text-xl font-bold">⚠️</div>\n'
            '    <h3 class="text-base font-bold text-slate-900 dark:text-slate-100">'
            "Falha no Envio do Arquivo</h3>\n"
            f'    <p class="text-xs text-slate-600 dark:text-slate-400">{exc}</p>\n'
            '    <button type="button" onclick="closeModal()" class="w-full py-2 bg-slate-900 '
            "text-white dark:bg-white dark:text-slate-900 rounded-xl text-xs font-bold "
            'cursor-pointer">Fechar</button>\n'
            "  </div>\n"
            "</div>"
        )
        return HTMLResponse(
            content=modal_html,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    api_key = resolve_gemini_api_key(current_user)
    parser = get_resume_parser_adapter(api_key=api_key)
    try:
        parsed_dto = await parser.parse_resume(
            file_bytes=file_bytes,
            mime_type=mime_type,
            filename=file.filename or "uploaded_resume",
        )
    except ResumeParserError as exc:
        logger.error("web_resume_parsing_error", error=str(exc))
        error_modal_html = (
            '<div id="import-review-modal-backdrop" class="fixed inset-0 z-50 flex '
            'items-center justify-center p-4 bg-slate-950/60" role="dialog" aria-modal="true">\n'
            '  <div class="bg-white dark:bg-slate-900 rounded-2xl p-6 max-w-md w-full '
            'border border-amber-200 dark:border-amber-900 shadow-xl text-center space-y-4">\n'
            '    <div class="w-12 h-12 rounded-full bg-amber-100 text-amber-600 '
            "dark:bg-amber-950 dark:text-amber-400 mx-auto flex items-center justify-center "
            'text-xl font-bold">⚠️</div>\n'
            '    <h3 class="text-base font-bold text-slate-900 dark:text-slate-100">'
            "Não foi possível analisar o currículo</h3>\n"
            f'    <p class="text-xs text-slate-600 dark:text-slate-400">{exc}</p>\n'
            '    <button type="button" onclick="closeModal()" class="w-full py-2 bg-slate-900 '
            "text-white dark:bg-white dark:text-slate-900 rounded-xl text-xs font-bold "
            'cursor-pointer">Fechar</button>\n'
            "  </div>\n"
            "</div>"
        )
        return HTMLResponse(
            content=error_modal_html,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    serialized = parsed_dto.model_dump_json()
    return templates.TemplateResponse(
        request=request,
        name="profile/partials/import_review_modal.html.jinja2",
        context={
            "request": request,
            "current_user": current_user,
            "parsed_dto": parsed_dto,
            "serialized_dto": serialized,
        },
    )


@router.post("/profile/confirm-import")
async def confirm_profile_import(
    payload: str = Form(...),
    current_user: User | None = Depends(get_authenticated_web_user),
    profile_service: ProfileService = Depends(get_profile_service),
) -> Response:
    """Confirma e persiste no banco de dados os dados extraídos aprovados pelo usuário."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    parsed_dto = ParsedProfileDTO.model_validate_json(payload)
    await profile_service.import_parsed_profile(user_id=current_user.id, parsed_profile=parsed_dto)
    logger.info("web_profile_import_confirmed", user_id=str(current_user.id))

    response = Response(status_code=status.HTTP_200_OK)
    response.headers["HX-Redirect"] = "/profile"
    return response
