import hmac
import html
import json
import secrets
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gemini_ai_adapter import GeminiAIAdapter
from app.api.v1.deps import (
    create_copilot_service,
    get_application_service,
    get_auth_service,
    get_document_service,
    get_job_ingest_service,
    get_profile_service,
    get_prompt_skill_service,
    get_resume_parser_adapter,
    get_resume_service,
    get_user_service,
    google_oauth_adapter,
    resolve_gemini_api_key,
    resolve_gemini_model,
    resolve_gemini_thinking_level,
)
from app.api.v1.schemas.application import (
    ApplicationCreate,
    ApplicationNoteCreate,
    ApplicationUpdate,
)
from app.api.v1.schemas.resume import ResumeGenerateRequest
from app.core.config import settings
from app.core.crypto import crypto_service
from app.core.database import get_db_session
from app.core.file_security import FileSecurityError, validate_resume_file
from app.core.grounding_audit import GroundingAuditEngine
from app.core.logging import get_logger
from app.core.rate_limit import limiter
from app.core.telemetry import set_user_id
from app.core.url_scraper import URLScraperError
from app.domain.models import (
    Application,
    ApplicationNote,
    GeneratedResume,
    PromptSkill,
    User,
    UserSettings,
)
from app.ports.ai_port import AIError, ChatMessage, ModelUnavailableError
from app.ports.oauth_port import OAuthError
from app.ports.resume_parser_port import ParsedProfileDTO, ResumeParserError
from app.services.application_service import ApplicationService
from app.services.auth_service import AuthService
from app.services.document_service import DocumentService
from app.services.job_ingest_service import JobIngestService
from app.services.profile_service import ProfileService
from app.services.prompt_skill_service import PromptSkillService
from app.services.resume_service import ResumeService
from app.services.user_service import UserService

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.autoescape = select_autoescape(["html", "xml", "jinja2"])


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
    profile_service: ProfileService = Depends(get_profile_service),
) -> Response:
    """Renderiza a página inicial para visitantes ou redireciona
    inteligentemente o usuário autenticado."""
    if current_user is not None:
        has_dossier = False
        if profile_service is not None and hasattr(profile_service, "has_dossier"):
            try:
                has_dossier = await profile_service.has_dossier(current_user.id)
            except Exception:  # pragma: no cover
                has_dossier = False
        target_url = "/applications" if has_dossier else "/profile"
        return RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)

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
@limiter.limit("10/minute")
async def login_google_redirect(request: Request) -> Response:
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
@limiter.limit("10/minute")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    auth_service: AuthService = Depends(get_auth_service),
    profile_service: ProfileService = Depends(get_profile_service),
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
    has_dossier = False
    if profile_service is not None and hasattr(profile_service, "has_dossier"):
        try:
            has_dossier = await profile_service.has_dossier(user.id)
        except Exception:  # pragma: no cover
            has_dossier = False
    target_url = "/applications" if has_dossier else "/profile"
    response = RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response=response, session_token=session_token)
    response.delete_cookie(key="oauth_state", path="/auth/callback/google")
    return response


@router.post("/auth/logout", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    current_user: User | None = Depends(get_authenticated_web_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Encerra a sessão Web do usuário removendo o cookie e invalidando no servidor."""
    if current_user is not None:
        await auth_service.revoke_session(current_user)
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
@limiter.limit("10/minute")
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
            '<div id="import-review-modal-backdrop" class="app-modal-backdrop" '
            'role="dialog" aria-modal="true">\n'
            '  <div class="app-modal-dialog max-w-md p-6 text-center space-y-4">\n'
            '    <div class="w-12 h-12 rounded-full bg-rose-100 text-rose-600 '
            "dark:bg-rose-950 dark:text-rose-400 mx-auto flex items-center justify-center "
            'text-xl font-bold">⚠️</div>\n'
            '    <h3 class="app-modal-title justify-center">'
            "Falha no Envio do Arquivo</h3>\n"
            f'    <p class="app-modal-subtitle text-slate-600 dark:text-slate-400">{exc}</p>\n'
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
    model = resolve_gemini_model(current_user)
    thinking_level = resolve_gemini_thinking_level(current_user)
    parser = get_resume_parser_adapter(api_key=api_key, model=model, thinking_level=thinking_level)
    try:
        parsed_dto = await parser.parse_resume(
            file_bytes=file_bytes,
            mime_type=mime_type,
            filename=file.filename or "uploaded_resume",
        )
    except ResumeParserError as exc:
        logger.error("web_resume_parsing_error", error=str(exc))
        is_missing_key = "não configurada" in str(exc).lower()
        if is_missing_key:
            error_modal_html = (
                '<div id="import-review-modal-backdrop" class="app-modal-backdrop" '
                'role="dialog" aria-modal="true" aria-labelledby="byok-modal-title">\n'
                '  <div class="app-modal-dialog max-w-md p-6 text-center space-y-4">\n'
                '    <div class="w-12 h-12 rounded-full bg-amber-100 text-amber-600 '
                "dark:bg-amber-950 dark:text-amber-400 mx-auto flex items-center justify-center "
                'text-xl font-bold">🔑</div>\n'
                '    <h3 id="byok-modal-title" class="app-modal-title justify-center">'
                "Chave do Gemini Não Configurada (100% BYOK)</h3>\n"
                '    <p class="app-modal-subtitle text-slate-600 '
                'dark:text-slate-400 leading-relaxed">\n'
                "      O ThothCVs AI opera sob o modelo <strong>100% BYOK</strong> "
                "(Bring Your Own Key) para garantir sua total privacidade e controle. "
                "Para extrair os dados factuais do seu currículo com IA, cadastre sua chave de "
                "API gratuita do Google AI Studio nas configurações.\n"
                "    </p>\n"
                '    <div class="flex flex-col sm:flex-row gap-2 pt-2">\n'
                '      <a href="/settings" class="inline-flex items-center justify-center gap-1.5 '
                "w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl "
                'text-xs font-bold transition-colors cursor-pointer shadow-xs">\n'
                "        ⚙️ Ir para Configurações\n"
                "      </a>\n"
                '      <button type="button" onclick="closeModal()" class="w-full sm:w-auto '
                "py-2.5 px-4 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 "
                "hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl text-xs font-semibold "
                'cursor-pointer">\n'
                "        Fechar\n"
                "      </button>\n"
                "    </div>\n"
                "  </div>\n"
                "</div>"
            )
        else:
            error_modal_html = (
                '<div id="import-review-modal-backdrop" class="app-modal-backdrop" '
                'role="dialog" aria-modal="true">\n'
                '  <div class="app-modal-dialog max-w-md p-6 text-center space-y-4">\n'
                '    <div class="w-12 h-12 rounded-full bg-amber-100 text-amber-600 '
                "dark:bg-amber-950 dark:text-amber-400 mx-auto flex items-center justify-center "
                'text-xl font-bold">⚠️</div>\n'
                '    <h3 class="app-modal-title justify-center">'
                "Não foi possível analisar o currículo</h3>\n"
                f'    <p class="app-modal-subtitle text-slate-600 dark:text-slate-400">{exc}</p>\n'
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


# ==================== GERADOR DE CURRÍCULO & TAILORING (WEB UI) ====================
@router.get("/resumes/new", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def new_resume_page(
    request: Request,
    current_user: User | None = Depends(get_authenticated_web_user),
    prompt_skill_service: PromptSkillService = Depends(get_prompt_skill_service),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Renderiza a página interativa de criação e tailoring de currículo sob medida."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    from app.services.token_service import get_user_token_usage

    error_msg = request.query_params.get("error")
    skills = await prompt_skill_service.list_active_skills(user_id=current_user.id)
    token_usage = await get_user_token_usage(db, current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="resumes/new.html.jinja2",
        context={
            "request": request,
            "current_user": current_user,
            "active_tab": "resumes",
            "skills": skills,
            "messages": [],
            "prompt_skill_slug": "google-xyz",
            "history_json": "[]",
            "job_description": "",
            "error_message": error_msg,
            "token_usage": token_usage,
        },
    )


@router.post("/resumes/scrape-job-url", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def scrape_job_url(
    request: Request,
    url: str = Form(...),
    current_user: User | None = Depends(get_authenticated_web_user),
    job_ingest_service: JobIngestService = Depends(get_job_ingest_service),
) -> Response:
    """Extrai com segurança o texto de uma vaga a partir de URL pública.

    Implementa blindagem rigorosa anti-SSRF (CWE-918).
    """
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        text = await job_ingest_service.extract_text_from_url(url=url)
    except (HTTPException, URLScraperError, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        logger.warning("web_job_url_scraping_failed", url=url, error=detail)
        safe_exc = html.escape(str(detail))
        return HTMLResponse(
            content=(
                '<div class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/60 border border-rose-200 '
                'dark:border-rose-900 text-xs text-rose-700 dark:text-rose-300 space-y-1">'
                f"<strong>⚠️ Falha ao extrair vaga:</strong> <span>{safe_exc}</span></div>"
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    escaped_json = json.dumps(text)
    response_content = (
        f"<script>\n"
        f"  var input = document.getElementById('job-description-input');\n"
        f"  if (input) {{\n"
        f"    input.value = {escaped_json};\n"
        f"    handleJobDescriptionChange(input.value);\n"
        f"  }}\n"
        f"</script>\n"
        '<div class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 '
        "dark:border-emerald-900 text-xs text-emerald-700 dark:text-emerald-300 "
        'flex items-center justify-between">\n'
        f"  <span>✅ Conteúdo da vaga importado com sucesso "
        f"({len(text)} caracteres extraídos).</span>\n"
        f"</div>"
    )
    return HTMLResponse(content=response_content, status_code=status.HTTP_200_OK)


@router.post("/resumes/upload-job-doc", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def upload_job_doc(
    request: Request,
    file: UploadFile = File(...),
    current_user: User | None = Depends(get_authenticated_web_user),
    job_ingest_service: JobIngestService = Depends(get_job_ingest_service),
) -> Response:
    """Extrai texto do anúncio da vaga a partir do upload de documento (PDF/DOCX)."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    file_bytes = await file.read()
    try:
        text = job_ingest_service.extract_text_from_document(
            file_bytes=file_bytes, filename=file.filename or "vaga.pdf"
        )
    except (HTTPException, FileSecurityError, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        logger.warning("web_job_doc_upload_failed", filename=file.filename, error=detail)
        safe_exc = html.escape(str(detail))
        return HTMLResponse(
            content=(
                '<div class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/60 border border-rose-200 '
                'dark:border-rose-900 text-xs text-rose-700 dark:text-rose-300 space-y-1">'
                f"<strong>⚠️ Falha ao ler documento:</strong> <span>{safe_exc}</span></div>"
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    escaped_json = json.dumps(text)
    response_content = (
        f"<script>\n"
        f"  var input = document.getElementById('job-description-input');\n"
        f"  if (input) {{\n"
        f"    input.value = {escaped_json};\n"
        f"    handleJobDescriptionChange(input.value);\n"
        f"  }}\n"
        f"</script>\n"
        '<div class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 '
        "dark:border-emerald-900 text-xs text-emerald-700 dark:text-emerald-300 "
        'flex items-center justify-between">\n'
        f"  <span>✅ Documento processado com sucesso "
        f"({len(text)} caracteres extraídos).</span>\n"
        f"</div>"
    )
    return HTMLResponse(content=response_content, status_code=status.HTTP_200_OK)


@router.post("/resumes/analyze-match", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def analyze_match(
    request: Request,
    job_description: str = Form(""),
    current_user: User | None = Depends(get_authenticated_web_user),
    resume_service: ResumeService = Depends(get_resume_service),
) -> Response:
    """Calcula a aderência semântica e lacunas contra o Dossiê Mestre do usuário."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if not job_description.strip():
        return HTMLResponse(
            content=(
                '<div id="match-analysis-container" class="bg-white dark:bg-slate-900 border '
                "border-amber-200 dark:border-amber-900 rounded-2xl p-6 shadow-sm text-xs "
                'text-amber-700 dark:text-amber-300">⚠️ Por favor, informe a descrição da vaga '
                "antes de calcular a aderência.</div>"
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    match_result = await resume_service.match_preview(
        user=current_user, job_description=job_description
    )
    return templates.TemplateResponse(
        request=request,
        name="resumes/partials/match_card.html.jinja2",
        context={"request": request, "match_result": match_result},
    )


@router.post("/resumes/copilot-chat", response_class=HTMLResponse)
@limiter.limit("20/minute")
async def copilot_chat_interaction(
    request: Request,
    message: str = Form(...),
    job_description: str = Form(""),
    prompt_skill_slug: str = Form("google-xyz"),
    history_json: str = Form("[]"),
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Interação conversacional com o Copilot de IA para refinamento de currículo."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    raw_history: list[dict[str, str]] = []
    try:
        raw_history = json.loads(history_json)
    except Exception:
        raw_history = []

    chat_messages = [
        ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
        for m in raw_history
        if "role" in m and "content" in m
    ]

    if not job_description.strip():
        return templates.TemplateResponse(
            request=request,
            name="resumes/partials/copilot_chat.html.jinja2",
            context={
                "request": request,
                "messages": chat_messages,
                "job_description": "",
                "prompt_skill_slug": prompt_skill_slug,
                "history_json": history_json,
                "error_message": (
                    "Por favor, preencha ou importe a descrição da vaga antes "
                    "de conversar com o Copilot."
                ),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    chat_messages.append(ChatMessage(role="user", content=message))
    copilot_service = create_copilot_service(db=db, user=current_user)

    try:
        reply = await copilot_service.chat(
            user=current_user,
            job_description=job_description,
            prompt_skill_slug=prompt_skill_slug,
            messages=chat_messages,
        )
        chat_messages.append(ChatMessage(role="assistant", content=reply))
        error_msg = None
    except ModelUnavailableError as exc:
        logger.warning("web_copilot_chat_model_unavailable", error=str(exc))
        error_msg = str(exc)
    except Exception as exc:
        logger.error("web_copilot_chat_error", error=str(exc), exc_info=True)
        error_msg = (
            "Falha ao comunicar com o assistente de IA. Por favor, tente novamente mais tarde."
        )

    updated_history = json.dumps([{"role": m.role, "content": m.content} for m in chat_messages])

    return templates.TemplateResponse(
        request=request,
        name="resumes/partials/copilot_chat.html.jinja2",
        context={
            "request": request,
            "messages": chat_messages,
            "job_description": job_description,
            "prompt_skill_slug": prompt_skill_slug,
            "history_json": updated_history,
            "error_message": error_msg,
        },
    )


@router.post("/resumes/generate-custom")
@limiter.limit("5/minute")
async def generate_custom_resume(
    request: Request,
    job_description: str = Form(...),
    prompt_skill_slug: str = Form("google-xyz"),
    language: str = Form("pt-BR"),
    model_choice: str | None = Form(None),
    current_user: User | None = Depends(get_authenticated_web_user),
    resume_service: ResumeService = Depends(get_resume_service),
) -> Response:
    """Dispara a geração de currículo inteligente e estruturado a partir da interface web."""
    is_ajax = request.headers.get(
        "x-requested-with"
    ) == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "")

    if current_user is None:
        logger.warning(
            "web_custom_resume_generation_unauthenticated",
            path=request.url.path,
        )
        if is_ajax:
            return JSONResponse(
                content={
                    "status": "error",
                    "message": "Autenticação necessária. Faça login novamente.",
                },
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    if model_choice:
        if ":" in model_choice:
            model_part, thinking_part = model_choice.split(":", 1)
        else:
            model_part, thinking_part = model_choice, "medium"

        stmt = select(UserSettings).where(UserSettings.user_id == current_user.id)
        res = await resume_service._db.execute(stmt)
        user_settings = res.scalar_one_or_none()
        if not user_settings:
            user_settings = UserSettings(user_id=current_user.id)
            resume_service._db.add(user_settings)
        user_settings.gemini_model = model_part
        user_settings.gemini_thinking_level = thinking_part
        current_user.settings = user_settings
        await resume_service._db.commit()

    logger.info(
        "web_custom_resume_generation_initiated",
        user_id=str(current_user.id),
        prompt_skill_slug=prompt_skill_slug,
        language=language,
        model_choice=model_choice,
        job_description_length=len(job_description),
    )

    try:
        result = await resume_service.generate_resume(
            user=current_user,
            payload=ResumeGenerateRequest(
                job_description=job_description,
                prompt_skill_slug=prompt_skill_slug,
                language=language,
            ),
        )
        logger.info(
            "web_custom_resume_generated",
            user_id=str(current_user.id),
            resume_id=str(result.resume_id),
            language=language,
        )
        redirect_url = f"/resumes/{result.resume_id}/preview"
        if is_ajax:
            return JSONResponse(
                content={
                    "status": "ok",
                    "resume_id": str(result.resume_id),
                    "redirect_url": redirect_url,
                }
            )
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    except HTTPException as exc:
        logger.warning(
            "web_custom_resume_generation_http_error",
            user_id=str(current_user.id),
            status_code=exc.status_code,
            detail=str(exc.detail),
        )
        safe_detail = (
            "Ocorreu uma falha no servidor ao gerar o currículo. Tente novamente mais tarde."
            if exc.status_code >= 500
            else str(exc.detail)
        )
        if is_ajax:
            return JSONResponse(
                content={"status": "error", "message": safe_detail},
                status_code=exc.status_code,
            )
        return RedirectResponse(
            url=f"/resumes/new?error={quote_plus(safe_detail)}",
            status_code=status.HTTP_302_FOUND,
        )
    except ModelUnavailableError as exc:
        logger.warning(
            "web_custom_resume_generation_model_unavailable",
            user_id=str(current_user.id),
            model=exc.model,
            error=str(exc),
        )
        if is_ajax:
            return JSONResponse(
                content={"status": "error", "message": str(exc)},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return RedirectResponse(
            url=f"/resumes/new?error={quote_plus(str(exc))}",
            status_code=status.HTTP_302_FOUND,
        )
    except (AIError, Exception) as exc:
        logger.error(
            "web_custom_resume_generation_failed",
            user_id=str(current_user.id),
            error=str(exc),
            exc_info=True,
        )
        err_msg = "Falha na geração do currículo com IA. Por favor, tente novamente."
        if is_ajax:
            return JSONResponse(
                content={"status": "error", "message": err_msg},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return RedirectResponse(
            url=f"/resumes/new?error={quote_plus(err_msg)}",
            status_code=status.HTTP_302_FOUND,
        )


@router.post("/resumes/{resume_id}/translate")
@limiter.limit("10/minute")
async def resume_translate_language(
    request: Request,
    resume_id: uuid.UUID,
    language: str = Form(...),
    current_user: User | None = Depends(get_authenticated_web_user),
    resume_service: ResumeService = Depends(get_resume_service),
) -> Response:
    """Traduz o currículo atual diretamente para o idioma selecionado
    mantendo fidelidade factual."""
    is_ajax = request.headers.get(
        "x-requested-with"
    ) == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "")

    if current_user is None:
        if is_ajax:
            return JSONResponse(
                content={
                    "status": "error",
                    "message": "Autenticação necessária. Faça login novamente.",
                },
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    logger.info(
        "web_resume_translation_initiated",
        user_id=str(current_user.id),
        resume_id=str(resume_id),
        target_language=language,
    )

    try:
        resume = await resume_service.translate_resume(
            user=current_user,
            resume_id=resume_id,
            target_language=language,
        )
        redirect_url = f"/resumes/{resume.id}/preview?tab=editor&translated=1"
        if is_ajax:
            from app.services.token_service import get_user_token_usage

            usage_data = await get_user_token_usage(resume_service._db, current_user.id)
            return JSONResponse(
                content={
                    "status": "ok",
                    "message": f"Currículo traduzido com sucesso para {language}!",
                    "redirect_url": redirect_url,
                    "tokens_used_today": usage_data["tokens_used_today"],
                    "formatted_tokens_today": usage_data["formatted_tokens_today"],
                }
            )
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    except ModelUnavailableError as exc:
        logger.warning(
            "web_resume_translation_model_unavailable",
            user_id=str(current_user.id),
            resume_id=str(resume_id),
            error=str(exc),
        )
        if is_ajax:
            return JSONResponse(
                content={"status": "error", "message": str(exc)},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return RedirectResponse(
            url=f"/resumes/{resume_id}/preview?tab=editor&error={quote_plus(str(exc))}",
            status_code=status.HTTP_302_FOUND,
        )
    except HTTPException as exc:
        logger.warning(
            "web_resume_translation_http_error",
            user_id=str(current_user.id),
            resume_id=str(resume_id),
            status_code=exc.status_code,
            detail=str(exc.detail),
        )
        if is_ajax:
            return JSONResponse(
                content={"status": "error", "message": str(exc.detail)},
                status_code=exc.status_code,
            )
        return RedirectResponse(
            url=f"/resumes/{resume_id}/preview?tab=editor&error={quote_plus(str(exc.detail))}",
            status_code=status.HTTP_302_FOUND,
        )
    except Exception as exc:
        logger.error(
            "web_resume_translation_failed",
            user_id=str(current_user.id),
            resume_id=str(resume_id),
            error=str(exc),
            exc_info=True,
        )
        err_msg = "Falha ao traduzir o currículo. Por favor, tente novamente."
        if is_ajax:
            return JSONResponse(
                content={"status": "error", "message": err_msg},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return RedirectResponse(
            url=f"/resumes/{resume_id}/preview?tab=editor&error={quote_plus(err_msg)}",
            status_code=status.HTTP_302_FOUND,
        )


def _extract_updated_resume_content(
    base_content: dict[str, Any],
    form_data: dict[str, Any],
) -> dict[str, Any]:
    """Extrai e mescla campos editados do formulário HTML com o JSON estruturado base."""
    content = dict(base_content)
    header = dict(content.get("header") or {})
    if "target_title" in form_data and form_data["target_title"]:
        header["target_title"] = str(form_data["target_title"]).strip()
    content["header"] = header

    if "language" in form_data and form_data["language"]:
        content["language"] = str(form_data["language"]).strip()

    if "professional_summary" in form_data and form_data["professional_summary"] is not None:
        content["professional_summary"] = str(form_data["professional_summary"]).strip()

    if "skills_list" in form_data and form_data["skills_list"] is not None:
        raw_skills = [s.strip() for s in str(form_data["skills_list"]).split(",") if s.strip()]
        content["skills_highlighted"] = raw_skills
        content["skills"] = raw_skills

    exp_indices: set[int] = set()
    for k in form_data:
        if k.startswith("exp_") and k.endswith("_title"):
            try:
                idx = int(k.split("_")[1])
                exp_indices.add(idx)
            except (IndexError, ValueError):
                pass

    if exp_indices:
        existing_exps = list(
            content.get("selected_experiences") or content.get("experiences") or []
        )
        updated_exps: list[dict[str, Any]] = []
        for idx in sorted(exp_indices):
            title = str(form_data.get(f"exp_{idx}_title", ""))
            company = str(form_data.get(f"exp_{idx}_company", ""))
            period = str(form_data.get(f"exp_{idx}_period", ""))
            bullets_raw = str(form_data.get(f"exp_{idx}_bullets", ""))
            bullet_points = [b.strip() for b in bullets_raw.splitlines() if b.strip()]

            base_exp = (
                existing_exps[idx]
                if idx < len(existing_exps) and isinstance(existing_exps[idx], dict)
                else {}
            )
            start_date = base_exp.get("start_date", "")
            end_date = base_exp.get("end_date", "")
            if period and "—" in period:
                parts = [p.strip() for p in period.split("—")]
                start_date = parts[0]
                end_date = parts[1] if len(parts) > 1 else ""
            elif period and "-" in period:
                parts = [p.strip() for p in period.split("-")]
                start_date = parts[0]
                end_date = parts[1] if len(parts) > 1 else ""
            elif period:
                start_date = period.strip()
                end_date = ""

            updated_exps.append(
                {
                    "position_title": title,
                    "company_name": company,
                    "start_date": start_date,
                    "end_date": end_date,
                    "tech_stack": (
                        [
                            t.strip()
                            for t in str(form_data.get(f"exp_{idx}_tech", "")).split(",")
                            if t.strip()
                        ]
                        if f"exp_{idx}_tech" in form_data
                        else base_exp.get("tech_stack", [])
                    ),
                    "bullet_points": bullet_points,
                    "achievements": bullet_points,
                }
            )
        content["selected_experiences"] = updated_exps
        content["experiences"] = updated_exps

    # Extrai formações acadêmicas editadas / adicionadas
    edu_indices: set[int] = set()
    for k in form_data:
        if k.startswith("edu_") and k.endswith("_degree"):
            try:
                idx = int(k.split("_")[1])
                edu_indices.add(idx)
            except (IndexError, ValueError):  # pragma: no cover
                pass

    if edu_indices:
        updated_edus: list[dict[str, Any]] = []
        for idx in sorted(edu_indices):
            degree = str(form_data.get(f"edu_{idx}_degree", "")).strip()
            institution = str(form_data.get(f"edu_{idx}_institution", "")).strip()
            field_of_study = str(form_data.get(f"edu_{idx}_field", "")).strip()
            period = str(form_data.get(f"edu_{idx}_period", "")).strip()
            start_date = period
            end_date = ""
            if period and "—" in period:
                parts = [p.strip() for p in period.split("—")]
                start_date = parts[0]
                end_date = parts[1] if len(parts) > 1 else ""
            elif period and "-" in period:
                parts = [p.strip() for p in period.split("-")]
                start_date = parts[0]
                end_date = parts[1] if len(parts) > 1 else ""

            if degree or institution:
                updated_edus.append(
                    {
                        "degree": degree,
                        "institution_name": institution,
                        "institution": institution,
                        "field_of_study": field_of_study,
                        "start_date": start_date,
                        "end_date": end_date,
                    }
                )
        content["education"] = updated_edus

    # Extrai certificações editadas / adicionadas
    cert_indices: set[int] = set()
    for k in form_data:
        if k.startswith("cert_") and k.endswith("_name"):
            try:
                idx = int(k.split("_")[1])
                cert_indices.add(idx)
            except (IndexError, ValueError):  # pragma: no cover
                pass

    if cert_indices:
        updated_certs: list[dict[str, Any]] = []
        for idx in sorted(cert_indices):
            name = str(form_data.get(f"cert_{idx}_name", "")).strip()
            issuer = str(form_data.get(f"cert_{idx}_issuer", "")).strip()
            if name:
                updated_certs.append(
                    {
                        "name": name,
                        "issuing_organization": issuer,
                        "issuer": issuer,
                    }
                )
        content["certifications"] = updated_certs

    return content


@router.get("/resumes/{resume_id}/preview", response_class=HTMLResponse)
async def resume_preview_page(
    request: Request,
    resume_id: uuid.UUID,
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Carrega o workspace integrado do currículo com preview ao vivo, dossiê mestre e copilot."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    stmt = select(GeneratedResume).where(
        GeneratedResume.id == resume_id,
        GeneratedResume.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    resume = result.scalar_one_or_none()

    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Currículo não encontrado.",
        )

    application = None
    if resume.application_id:
        stmt_app = select(Application).where(Application.id == resume.application_id)
        res_app = await db.execute(stmt_app)
        application = res_app.scalar_one_or_none()

    # 1. Recupera o Dossiê Mestre factual completo do candidato
    full_dossier: dict[str, Any] = {
        "experiences": [],
        "educations": [],
        "certifications": [],
        "projects": [],
        "skills": [],
        "languages": [],
    }
    try:
        profile_service = ProfileService(db)
        full_dossier = await profile_service.get_full_dossier(current_user.id)
    except Exception as exc:  # pragma: no cover
        logger.debug("web_preview_dossier_fetch_fallback", error=str(exc))

    # 2. Carrega histórico de conversa com o Copilot IA vinculado à oportunidade
    chat_messages: list[ChatMessage] = []
    copilot_notes: list[Any] = []
    if resume.application_id:
        try:
            stmt_notes = (
                select(ApplicationNote)
                .where(
                    ApplicationNote.application_id == resume.application_id,
                    ApplicationNote.note_type == "copilot_chat",
                )
                .order_by(ApplicationNote.created_at.asc())
            )
            res_notes = await db.execute(stmt_notes)
            copilot_notes = list(res_notes.scalars().all())
        except Exception:  # pragma: no cover
            if application and hasattr(application, "notes"):
                copilot_notes = [
                    n
                    for n in (application.notes or [])
                    if getattr(n, "note_type", "") == "copilot_chat"
                ]

    for n in copilot_notes:
        raw_text = getattr(n, "content", "")
        if raw_text.startswith("👤 Candidato: "):
            chat_messages.append(
                ChatMessage(role="user", content=raw_text[len("👤 Candidato: ") :])
            )
        elif raw_text.startswith("🤖 Copilot IA: "):
            chat_messages.append(
                ChatMessage(role="assistant", content=raw_text[len("🤖 Copilot IA: ") :])
            )
        elif raw_text.startswith("🤖 Copilot: "):
            chat_messages.append(
                ChatMessage(role="assistant", content=raw_text[len("🤖 Copilot: ") :])
            )
        else:
            chat_messages.append(ChatMessage(role="assistant", content=raw_text))

    history_json = json.dumps([{"role": m.role, "content": m.content} for m in chat_messages])

    prompt_skill_slug = "google-xyz"
    if resume.prompt_skill_id:
        try:
            stmt_ps = select(PromptSkill).where(PromptSkill.id == resume.prompt_skill_id)
            res_ps = await db.execute(stmt_ps)
            ps = res_ps.scalar_one_or_none()
            if ps and ps.slug:
                prompt_skill_slug = ps.slug
        except Exception:  # pragma: no cover
            pass

    return templates.TemplateResponse(
        request=request,
        name="resumes/preview.html.jinja2",
        context={
            "request": request,
            "resume": resume,
            "application": application,
            "content": resume.structured_content,
            "full_dossier": full_dossier,
            "chat_messages": chat_messages,
            "history_json": history_json,
            "prompt_skill_slug": prompt_skill_slug,
            "current_user": current_user,
            "active_tab": "resumes",
        },
    )


@router.post("/resumes/{resume_id}/copilot-chat", response_class=HTMLResponse)
async def resume_preview_copilot_chat(
    request: Request,
    resume_id: uuid.UUID,
    message: str = Form(...),
    prompt_skill_slug: str = Form("google-xyz"),
    history_json: str = Form("[]"),
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Interação conversacional com o Copilot no Live Editor, persistindo histórico na vaga."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    stmt = select(GeneratedResume).where(
        GeneratedResume.id == resume_id,
        GeneratedResume.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Currículo não encontrado."
        )

    application = None
    if resume.application_id:
        stmt_app = select(Application).where(Application.id == resume.application_id)
        res_app = await db.execute(stmt_app)
        application = res_app.scalar_one_or_none()

    raw_history: list[dict[str, str]] = []
    try:
        raw_history = json.loads(history_json)
    except Exception:
        raw_history = []

    chat_messages = [
        ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
        for m in raw_history
        if "role" in m and "content" in m
    ]

    clean_message = message.strip()
    if not clean_message:
        return templates.TemplateResponse(
            request=request,
            name="resumes/partials/preview_copilot_chat.html.jinja2",
            context={
                "request": request,
                "resume": resume,
                "application": application,
                "messages": chat_messages,
                "prompt_skill_slug": prompt_skill_slug,
                "history_json": history_json,
                "error_message": "Por favor, digite uma mensagem para o Copilot.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    chat_messages.append(ChatMessage(role="user", content=clean_message))
    copilot_service = create_copilot_service(db=db, user=current_user)

    job_description = (
        application.job_description
        if application and application.job_description
        else "Oportunidade de Engenharia e Tecnologia"
    )

    error_msg = None
    total_tokens = 0
    start_time = time.perf_counter()
    try:
        reply = await copilot_service.chat(
            user=current_user,
            job_description=job_description,
            prompt_skill_slug=prompt_skill_slug,
            messages=chat_messages,
        )
        chat_messages.append(ChatMessage(role="assistant", content=reply))

        # Persiste histórico de conversa na vaga (ApplicationNote)
        if resume.application_id:
            note_user = ApplicationNote(
                application_id=resume.application_id,
                content=f"👤 Candidato: {clean_message}",
                note_type="copilot_chat",
            )
            note_ai = ApplicationNote(
                application_id=resume.application_id,
                content=f"🤖 Copilot IA: {reply}",
                note_type="copilot_chat",
            )
            db.add(note_user)
            db.add(note_ai)
            if application:
                application.last_activity_at = datetime.now(UTC)
            await db.commit()

        raw_tokens = getattr(copilot_service._ai_port, "last_token_usage", 0)
        total_tokens = raw_tokens if isinstance(raw_tokens, int) else 0
        if total_tokens > 0:
            from app.services.token_service import record_token_usage

            await record_token_usage(db, current_user, total_tokens)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "web_preview_copilot_chat_turn_completed",
            resume_id=str(resume.id),
            application_id=str(resume.application_id),
            user_id=str(current_user.id),
            duration_ms=duration_ms,
            total_tokens=total_tokens,
        )
    except ModelUnavailableError as exc:
        logger.warning("web_preview_copilot_chat_model_unavailable", error=str(exc))
        error_msg = str(exc)
    except Exception as exc:
        logger.error("web_preview_copilot_chat_error", error=str(exc), exc_info=True)
        error_msg = (
            "Falha ao comunicar com o assistente de IA. Por favor, tente novamente mais tarde."
        )

    updated_history = json.dumps([{"role": m.role, "content": m.content} for m in chat_messages])

    response = templates.TemplateResponse(
        request=request,
        name="resumes/partials/preview_copilot_chat.html.jinja2",
        context={
            "request": request,
            "resume": resume,
            "application": application,
            "messages": chat_messages,
            "prompt_skill_slug": prompt_skill_slug,
            "history_json": updated_history,
            "error_message": error_msg,
        },
    )
    if total_tokens > 0:
        response.headers["HX-Trigger"] = json.dumps({"refreshTokens": True})
    return response


@router.post("/resumes/{resume_id}/regenerate-from-chat")
async def resume_preview_regenerate_from_chat(
    request: Request,
    resume_id: uuid.UUID,
    history_json: str = Form("[]"),
    prompt_skill_slug: str = Form("google-xyz"),
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
    resume_service: ResumeService = Depends(get_resume_service),
) -> Response:
    """Regera uma nova versão calibrada do currículo com base no histórico do Copilot Chat."""
    if current_user is None:
        if "HX-Request" in request.headers:
            resp = Response(status_code=status.HTTP_401_UNAUTHORIZED)
            resp.headers["HX-Redirect"] = "/?auth_error=login_required"
            return resp
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    raw_history: list[dict[str, str]] = []
    try:
        raw_history = json.loads(history_json)
    except Exception:
        raw_history = []

    chat_messages = [
        ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
        for m in raw_history
        if "role" in m and "content" in m
    ]

    if not chat_messages:
        stmt = select(GeneratedResume).where(
            GeneratedResume.id == resume_id,
            GeneratedResume.user_id == current_user.id,
        )
        res_res = await db.execute(stmt)
        resume = res_res.scalar_one_or_none()
        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Currículo não encontrado."
            )

        application = None
        if resume.application_id:
            stmt_app = select(Application).where(Application.id == resume.application_id)
            res_app = await db.execute(stmt_app)
            application = res_app.scalar_one_or_none()

        return templates.TemplateResponse(
            request=request,
            name="resumes/partials/preview_copilot_chat.html.jinja2",
            context={
                "request": request,
                "resume": resume,
                "application": application,
                "messages": [],
                "prompt_skill_slug": prompt_skill_slug,
                "history_json": history_json,
                "error_message": (
                    "Por favor, converse com o Copilot antes de solicitar a regeração da versão."
                ),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        new_resume_res = await resume_service.regenerate_resume_from_chat(
            user=current_user,
            resume_id=resume_id,
            chat_messages=chat_messages,
            prompt_skill_slug=prompt_skill_slug,
        )
        await db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("web_preview_regenerate_from_chat_failed", error=str(exc), exc_info=True)
        stmt = select(GeneratedResume).where(
            GeneratedResume.id == resume_id,
            GeneratedResume.user_id == current_user.id,
        )
        res_res = await db.execute(stmt)
        resume = res_res.scalar_one_or_none()
        application = None
        if resume and resume.application_id:
            stmt_app = select(Application).where(Application.id == resume.application_id)
            res_app = await db.execute(stmt_app)
            application = res_app.scalar_one_or_none()

        return templates.TemplateResponse(
            request=request,
            name="resumes/partials/preview_copilot_chat.html.jinja2",
            context={
                "request": request,
                "resume": resume,
                "application": application,
                "messages": chat_messages,
                "prompt_skill_slug": prompt_skill_slug,
                "history_json": history_json,
                "error_message": f"Falha na regeração da versão: {exc}",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    redirect_target = f"/resumes/{new_resume_res.resume_id}?tab=editor"
    if "HX-Request" in request.headers:
        response = Response(status_code=status.HTTP_200_OK)
        response.headers["HX-Redirect"] = redirect_target
        return response

    return RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/resumes/{resume_id}/preview-render", response_class=HTMLResponse)
async def resume_preview_render(
    request: Request,
    resume_id: uuid.UUID,
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Renderiza a folha A4 dinamicamente com base nas alterações do editor."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    stmt = select(GeneratedResume).where(
        GeneratedResume.id == resume_id,
        GeneratedResume.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Currículo não encontrado."
        )

    form_data = dict(await request.form())
    updated_content = _extract_updated_resume_content(resume.structured_content, form_data)

    return templates.TemplateResponse(
        request=request,
        name="resumes/partials/preview_paper.html.jinja2",
        context={
            "request": request,
            "resume": resume,
            "content": updated_content,
            "current_user": current_user,
        },
    )


@router.post("/resumes/{resume_id}/save", response_class=HTMLResponse)
async def resume_save_content(
    request: Request,
    resume_id: uuid.UUID,
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Persiste as edições manuais realizadas no currículo estruturado."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    stmt = select(GeneratedResume).where(
        GeneratedResume.id == resume_id,
        GeneratedResume.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Currículo não encontrado."
        )

    form_data = dict(await request.form())
    updated_content = _extract_updated_resume_content(resume.structured_content, form_data)
    resume.structured_content = updated_content
    if "language" in form_data and form_data["language"]:
        resume.language = str(form_data["language"]).strip()
    resume.updated_at = datetime.now(UTC)
    await db.commit()

    logger.info(
        "web_resume_saved",
        resume_id=str(resume.id),
        user_id=str(current_user.id),
    )

    toast_html = (
        '<div class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 '
        "border border-emerald-200 dark:border-emerald-800 text-xs font-semibold "
        "text-emerald-800 dark:text-emerald-300 flex items-center justify-between "
        'animate-in fade-in">\n'
        "  <span>✅ Alterações do currículo salvas com sucesso!</span>\n"
        '  <button type="button" onclick="this.parentElement.remove()" '
        'class="text-emerald-600 dark:text-emerald-400 hover:opacity-80 cursor-pointer">'
        "✕</button>\n"
        "</div>"
    )
    return HTMLResponse(content=toast_html)


@router.post("/resumes/{resume_id}/verify-grounding", response_class=HTMLResponse)
async def resume_verify_grounding(
    request: Request,
    resume_id: uuid.UUID,
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Audita a fidelidade factual do currículo editado contra o dossiê mestre do usuário."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    stmt = select(GeneratedResume).where(
        GeneratedResume.id == resume_id,
        GeneratedResume.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Currículo não encontrado."
        )

    start_time = time.perf_counter()
    form_data = dict(await request.form())
    updated_content = _extract_updated_resume_content(resume.structured_content, form_data)

    profile_service = ProfileService(db)
    raw_dossier = await profile_service.get_full_dossier(current_user.id)
    user_dossier: dict[str, Any] = {
        "companies": [e.company_name for e in raw_dossier.get("experiences", [])],
        "skills": [s.name for s in raw_dossier.get("skills", [])],
        "degrees": [e.degree for e in raw_dossier.get("educations", [])],
    }

    audit_engine = GroundingAuditEngine()
    audit = audit_engine.audit(updated_content, user_dossier)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    logger.info(
        "web_resume_grounding_audited",
        resume_id=str(resume.id),
        user_id=str(current_user.id),
        trust_score=audit.trust_score,
        hallucinations_count=len(audit.hallucinations),
        duration_ms=duration_ms,
    )

    return templates.TemplateResponse(
        request=request,
        name="resumes/partials/grounding_audit_card.html.jinja2",
        context={"request": request, "audit": audit},
    )


@router.get("/resumes/{resume_id}/export/pdf")
async def resume_export_pdf(
    resume_id: uuid.UUID,
    current_user: User | None = Depends(get_authenticated_web_user),
    document_service: DocumentService = Depends(get_document_service),
) -> Response:
    """Exporta o currículo gerado no formato binário PDF de alta fidelidade ATS."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    start_time = time.perf_counter()
    pdf_bytes, filename = await document_service.export_pdf(resume_id, current_user)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    logger.info(
        "web_resume_pdf_exported",
        resume_id=str(resume_id),
        user_id=str(current_user.id),
        duration_ms=duration_ms,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/resumes/{resume_id}/export/docx")
async def resume_export_docx(
    resume_id: uuid.UUID,
    current_user: User | None = Depends(get_authenticated_web_user),
    document_service: DocumentService = Depends(get_document_service),
) -> Response:
    """Exporta o currículo gerado no formato binário DOCX editável."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    start_time = time.perf_counter()
    docx_bytes, filename = await document_service.export_docx(resume_id, current_user)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    logger.info(
        "web_resume_docx_exported",
        resume_id=str(resume_id),
        user_id=str(current_user.id),
        duration_ms=duration_ms,
    )

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/applications", response_class=HTMLResponse)
async def applications_page(
    request: Request,
    current_user: User | None = Depends(get_authenticated_web_user),
    app_service: ApplicationService = Depends(get_application_service),
) -> Response:
    """Exibe o funil ATS pessoal completo com métricas e visualização Kanban."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    apps = await app_service.list_applications(current_user)
    applications_by_status = {
        col: [a for a in apps if a.status == col]
        for col in ["applied", "screen", "tech_interview", "final_interview", "offer", "rejected"]
    }
    analytics = await app_service.get_analytics_metrics(current_user)

    return templates.TemplateResponse(
        request=request,
        name="applications/index.html.jinja2",
        context={
            "request": request,
            "applications_by_status": applications_by_status,
            "analytics": analytics,
            "current_user": current_user,
            "active_tab": "applications",
        },
    )


@router.get("/applications/modal/create", response_class=HTMLResponse)
async def application_create_modal(
    request: Request,
    current_user: User | None = Depends(get_authenticated_web_user),
) -> Response:
    """Renderiza o modal acessível para registro de nova oportunidade."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    return templates.TemplateResponse(
        request=request,
        name="applications/partials/create_modal.html.jinja2",
        context={"request": request},
    )


@router.post("/applications/create")
async def application_create(
    request: Request,
    company_name: str = Form(...),
    job_title: str = Form(...),
    status_field: str = Form("applied", alias="status"),
    work_model: str = Form("remote"),
    salary_range: str | None = Form(None),
    location: str | None = Form(None),
    job_url: str | None = Form(None),
    job_description: str = Form(""),
    current_user: User | None = Depends(get_authenticated_web_user),
    app_service: ApplicationService = Depends(get_application_service),
) -> Response:
    """Cria uma nova candidatura no funil ATS e atualiza a visualização."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    payload = ApplicationCreate(
        company_name=company_name,
        job_title=job_title,
        status=status_field,
        work_model=work_model,
        salary_range=salary_range or None,
        location=location or None,
        job_url=job_url or None,
        job_description=job_description,
    )
    created = await app_service.create_application(current_user, payload)

    logger.info(
        "web_application_created",
        application_id=str(created.id),
        user_id=str(current_user.id),
        company=company_name,
    )

    if request.headers.get("HX-Request"):
        return Response(headers={"HX-Redirect": "/applications"})
    return RedirectResponse(url="/applications", status_code=status.HTTP_302_FOUND)


@router.post("/applications/{application_id}/status", response_class=HTMLResponse)
async def application_status_update(
    request: Request,
    application_id: uuid.UUID,
    new_status: str = Form(...),
    current_user: User | None = Depends(get_authenticated_web_user),
    app_service: ApplicationService = Depends(get_application_service),
) -> Response:
    """Avança o status da vaga no funil e retorna o tabuleiro Kanban atualizado."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    await app_service.update_application(
        user=current_user,
        app_id=application_id,
        payload=ApplicationUpdate(status=new_status),
    )

    logger.info(
        "web_application_status_updated",
        application_id=str(application_id),
        user_id=str(current_user.id),
        new_status=new_status,
    )

    apps = await app_service.list_applications(current_user)
    applications_by_status = {
        col: [a for a in apps if a.status == col]
        for col in ["applied", "screen", "tech_interview", "final_interview", "offer", "rejected"]
    }

    return templates.TemplateResponse(
        request=request,
        name="applications/partials/kanban_board.html.jinja2",
        context={
            "request": request,
            "applications_by_status": applications_by_status,
        },
    )


@router.get("/applications/{application_id}/detail", response_class=HTMLResponse)
async def application_detail_modal(
    request: Request,
    application_id: uuid.UUID,
    current_user: User | None = Depends(get_authenticated_web_user),
    app_service: ApplicationService = Depends(get_application_service),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Renderiza modal com histórico, notas e currículos vinculados à oportunidade."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    app_detail = await app_service.get_application_detail(current_user, application_id)
    stmt_resumes = (
        select(GeneratedResume)
        .where(
            GeneratedResume.application_id == application_id,
            GeneratedResume.user_id == current_user.id,
        )
        .order_by(GeneratedResume.version_number.desc())
    )
    res_resumes = await db.execute(stmt_resumes)
    resumes = res_resumes.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="applications/partials/detail_modal.html.jinja2",
        context={
            "request": request,
            "app": app_detail,
            "resumes": resumes,
        },
    )


@router.post("/applications/{application_id}/notes", response_class=HTMLResponse)
async def application_add_note(
    request: Request,
    application_id: uuid.UUID,
    content: str = Form(...),
    note_type: str = Form("general"),
    current_user: User | None = Depends(get_authenticated_web_user),
    app_service: ApplicationService = Depends(get_application_service),
) -> Response:
    """Registra uma nova anotação na vaga e retorna o feed de notas atualizado."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    await app_service.add_note(
        user=current_user,
        app_id=application_id,
        payload=ApplicationNoteCreate(content=content, note_type=note_type),
    )

    logger.info(
        "web_application_note_created",
        application_id=str(application_id),
        user_id=str(current_user.id),
        note_type=note_type,
    )

    app_detail = await app_service.get_application_detail(current_user, application_id)

    return templates.TemplateResponse(
        request=request,
        name="applications/partials/notes_section.html.jinja2",
        context={
            "request": request,
            "app": app_detail,
            "notes": app_detail.notes,
        },
    )


# ==============================================================================
# SPRINT 4: CONFIGURAÇÕES, BYOK GEMINI, I18N & CONFORMIDADE LGPD
# ==============================================================================


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Exibe a central de configurações, chave BYOK Gemini, idioma e LGPD."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    stmt = select(UserSettings).where(UserSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    user_settings = result.scalar_one_or_none()

    return templates.TemplateResponse(
        request=request,
        name="settings/index.html.jinja2",
        context={
            "request": request,
            "user_settings": user_settings,
            "current_user": current_user,
            "active_tab": "settings",
        },
    )


@router.post("/settings/gemini-key", response_class=HTMLResponse)
async def settings_save_gemini_key(
    request: Request,
    gemini_api_key: str = Form(""),
    gemini_model: str = Form("gemini-3.8-flash"),
    gemini_thinking_level: str = Form("medium"),
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Cifra via AES-GCM-256 com AAD e persiste a chave do Gemini e preferências de modelo."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    clean_key = gemini_api_key.strip()
    stmt = select(UserSettings).where(UserSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    user_settings = result.scalar_one_or_none()

    if not clean_key and (not user_settings or not user_settings.encrypted_gemini_api_key):
        error_html = (
            '<div class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/60 '
            "border border-rose-200 dark:border-rose-800 text-xs font-semibold "
            "text-rose-800 dark:text-rose-300 flex items-center justify-between "
            'animate-in fade-in">\n'
            "  <span>⚠️ A chave de API não pode estar em branco.</span>\n"
            '  <button type="button" onclick="this.parentElement.remove()" '
            'class="text-rose-600 dark:text-rose-400 hover:opacity-80 cursor-pointer">✕</button>\n'
            "</div>"
        )
        return HTMLResponse(content=error_html, status_code=status.HTTP_400_BAD_REQUEST)

    user_aad = str(current_user.id).encode("utf-8")
    encrypted_key: str | None = None
    if clean_key:
        encrypted_key = crypto_service.encrypt(clean_key, associated_data=user_aad)
    elif user_settings:
        encrypted_key = user_settings.encrypted_gemini_api_key

    clean_model = gemini_model.strip() or "gemini-3.8-flash"
    if clean_model in ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"):
        clean_model = "gemini-3.8-flash"
    clean_thinking = gemini_thinking_level.strip().lower() or "medium"
    if clean_thinking not in ("low", "medium", "high"):
        clean_thinking = "medium"

    if not user_settings:
        user_settings = UserSettings(
            user_id=current_user.id,
            encrypted_gemini_api_key=encrypted_key,
            gemini_model=clean_model,
            gemini_thinking_level=clean_thinking,
        )
        db.add(user_settings)
    else:
        if clean_key:
            user_settings.encrypted_gemini_api_key = encrypted_key
        user_settings.gemini_model = clean_model
        user_settings.gemini_thinking_level = clean_thinking
        user_settings.updated_at = datetime.now(UTC)

    await db.commit()

    logger.info(
        "web_gemini_key_saved",
        user_id=str(current_user.id),
        model=clean_model,
        thinking_level=clean_thinking,
    )

    success_html = (
        '<div class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 '
        "border border-emerald-200 dark:border-emerald-800 text-xs font-semibold "
        "text-emerald-800 dark:text-emerald-300 flex items-center justify-between "
        'animate-in fade-in">\n'
        "  <span>✅ Chave do Google Gemini salva e cifrada com sucesso (AES-GCM-256 com AAD). "
        f"Modelo: <strong>{clean_model}</strong> (Thinking: {clean_thinking.upper()}).</span>\n"
        '  <button type="button" onclick="this.parentElement.remove()" '
        'class="text-emerald-600 dark:text-emerald-400 hover:opacity-80 cursor-pointer">'
        "✕</button>\n"
        "</div>"
    )
    return HTMLResponse(content=success_html)


@router.post("/settings/gemini-key/test", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def settings_test_gemini_key(
    request: Request,
    gemini_api_key: str = Form(""),
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Testa a conectividade da chave informada ou persistida com o Google AI Studio."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    key_to_test = gemini_api_key.strip()
    if not key_to_test:
        stmt = select(UserSettings).where(UserSettings.user_id == current_user.id)
        result = await db.execute(stmt)
        user_settings = result.scalar_one_or_none()
        if user_settings and user_settings.encrypted_gemini_api_key:
            user_aad = str(current_user.id).encode("utf-8")
            try:
                key_to_test = crypto_service.decrypt(
                    user_settings.encrypted_gemini_api_key, associated_data=user_aad
                )
            except Exception as exc:
                logger.warning(
                    "web_gemini_key_decrypt_failed",
                    user_id=str(current_user.id),
                    error=str(exc),
                )
                key_to_test = ""

    if not key_to_test:
        warn_html = (
            '<div class="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/60 '
            "border border-amber-200 dark:border-amber-800 text-xs font-semibold "
            "text-amber-800 dark:text-amber-300 flex items-center justify-between "
            'animate-in fade-in">\n'
            "  <span>⚠️ Nenhuma chave informada ou cadastrada para teste.</span>\n"
            '  <button type="button" onclick="this.parentElement.remove()" '
            'class="text-amber-600 dark:text-amber-400 hover:opacity-80 cursor-pointer">'
            "✕</button>\n"
            "</div>"
        )
        return HTMLResponse(content=warn_html)

    start_time = time.perf_counter()
    try:
        model = resolve_gemini_model(current_user)
        thinking_level = resolve_gemini_thinking_level(current_user)
        adapter = GeminiAIAdapter(api_key=key_to_test, model=model, thinking_level=thinking_level)
        await adapter.analyze_job("Software Engineer Python")
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "web_gemini_key_test_success",
            user_id=str(current_user.id),
            duration_ms=duration_ms,
        )
        success_html = (
            '<div class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 '
            "border border-emerald-200 dark:border-emerald-800 text-xs font-semibold "
            "text-emerald-800 dark:text-emerald-300 flex items-center justify-between "
            'animate-in fade-in">\n'
            f"  <span>⚡ Conexão com a Google Gemini API validada com sucesso! "
            f"({duration_ms}ms)</span>\n"
            '  <button type="button" onclick="this.parentElement.remove()" '
            'class="text-emerald-600 dark:text-emerald-400 hover:opacity-80 cursor-pointer">'
            "✕</button>\n"
            "</div>"
        )
        return HTMLResponse(content=success_html)
    except ModelUnavailableError as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(
            "web_gemini_key_test_model_unavailable",
            user_id=str(current_user.id),
            error=str(exc),
            duration_ms=duration_ms,
        )
        fail_html = (
            '<div class="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/60 '
            "border border-amber-200 dark:border-amber-800 text-xs font-semibold "
            "text-amber-800 dark:text-amber-300 flex items-center justify-between "
            'animate-in fade-in">\n'
            f"  <span>⚠️ {exc}</span>\n"
            '  <button type="button" onclick="this.parentElement.remove()" '
            'class="text-amber-600 dark:text-amber-400 hover:opacity-80 '
            'cursor-pointer">✕</button>\n'
            "</div>"
        )
        return HTMLResponse(content=fail_html)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(
            "web_gemini_key_test_failed",
            user_id=str(current_user.id),
            error=str(exc),
            duration_ms=duration_ms,
            exc_info=True,
        )
        fail_html = (
            '<div class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/60 '
            "border border-rose-200 dark:border-rose-800 text-xs font-semibold "
            "text-rose-800 dark:text-rose-300 flex items-center justify-between "
            'animate-in fade-in">\n'
            "  <span>❌ Falha ao validar a chave com o Google AI Studio. "
            "Verifique se a chave é válida e tente novamente.</span>\n"
            '  <button type="button" onclick="this.parentElement.remove()" '
            'class="text-rose-600 dark:text-rose-400 hover:opacity-80 cursor-pointer">✕</button>\n'
            "</div>"
        )
        return HTMLResponse(content=fail_html)


@router.post("/settings/gemini-key/remove", response_class=HTMLResponse)
async def settings_remove_gemini_key(
    request: Request,
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Remove a chave pessoal do Gemini e restaura o uso da cota padrão compartilhada."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    stmt = select(UserSettings).where(UserSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    user_settings = result.scalar_one_or_none()

    if user_settings:
        user_settings.encrypted_gemini_api_key = None
        user_settings.updated_at = datetime.now(UTC)
        await db.commit()

    logger.info("web_gemini_key_removed", user_id=str(current_user.id))

    info_html = (
        '<div class="p-3 rounded-xl bg-slate-100 dark:bg-slate-800 '
        "border border-slate-200 dark:border-slate-700 text-xs font-semibold "
        "text-slate-800 dark:text-slate-200 flex items-center justify-between "
        'animate-in fade-in">\n'
        "  <span>ℹ️ Chave pessoal removida. "
        "O sistema agora utilizará a cota padrão compartilhada.</span>\n"
        '  <button type="button" onclick="this.parentElement.remove()" '
        'class="text-slate-500 hover:opacity-80 cursor-pointer">✕</button>\n'
        "</div>"
    )
    return HTMLResponse(content=info_html)


@router.post("/settings/quick-model")
@limiter.limit("30/minute")
async def settings_update_quick_model(
    request: Request,
    model_choice: str = Form(...),
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Atualiza o modelo de IA e nível de reflexão (thinking) do usuário."""
    if current_user is None:
        return JSONResponse(
            content={
                "status": "error",
                "message": "Autenticação necessária. Faça login novamente.",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if ":" in model_choice:
        model_part, thinking_part = model_choice.split(":", 1)
    else:
        model_part, thinking_part = model_choice, "medium"

    clean_model = model_part.strip() or "gemini-3.8-flash"
    if clean_model in ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"):
        clean_model = "gemini-3.8-flash"

    clean_thinking = thinking_part.strip().lower() or "medium"
    if clean_thinking not in ("low", "medium", "high"):
        clean_thinking = "medium"

    stmt = select(UserSettings).where(UserSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        user_settings = UserSettings(
            user_id=current_user.id,
            gemini_model=clean_model,
            gemini_thinking_level=clean_thinking,
        )
        db.add(user_settings)
    else:
        user_settings.gemini_model = clean_model
        user_settings.gemini_thinking_level = clean_thinking
        user_settings.updated_at = datetime.now(UTC)

    await db.commit()

    logger.info(
        "web_quick_model_saved",
        user_id=str(current_user.id),
        model=clean_model,
        thinking_level=clean_thinking,
    )

    return JSONResponse(
        content={
            "status": "ok",
            "model": clean_model,
            "thinking_level": clean_thinking,
            "message": f"Modelo atualizado para {clean_model} ({clean_thinking}).",
        }
    )


@router.get("/settings/tokens")
async def settings_get_tokens(
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Retorna métricas em tempo real do medidor de consumo de tokens do usuário."""
    if current_user is None:
        return JSONResponse(
            content={"status": "error", "message": "Autenticação necessária."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    from app.services.token_service import get_user_token_usage

    usage_data = await get_user_token_usage(db, current_user.id)
    return JSONResponse(
        content={
            "status": "ok",
            **usage_data,
        }
    )


@router.post("/settings/language", response_class=HTMLResponse)
async def settings_update_language(
    request: Request,
    response: Response,
    preferred_language: str = Form(...),
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Atualiza o idioma e dialeto padrão de interface e síntese de currículos."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    stmt = select(UserSettings).where(UserSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        user_settings = UserSettings(
            user_id=current_user.id,
            preferred_language=preferred_language,
        )
        db.add(user_settings)
    else:
        user_settings.preferred_language = preferred_language
        user_settings.updated_at = datetime.now(UTC)

    await db.commit()

    logger.info(
        "web_language_updated",
        user_id=str(current_user.id),
        preferred_language=preferred_language,
    )

    escaped_lang = html.escape(preferred_language)
    success_html = (
        '<div class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 '
        "border border-emerald-200 dark:border-emerald-800 text-xs font-semibold "
        "text-emerald-800 dark:text-emerald-300 flex items-center justify-between "
        'animate-in fade-in">\n'
        f"  <span>✅ Idioma padrão atualizado para <strong>{escaped_lang}</strong> "
        f"com sucesso!</span>\n"
        '  <button type="button" onclick="this.parentElement.remove()" '
        'class="text-emerald-600 dark:text-emerald-400 hover:opacity-80 cursor-pointer">'
        "✕</button>\n"
        "</div>"
    )
    res = HTMLResponse(content=success_html)
    res.set_cookie(
        key="locale",
        value=preferred_language,
        max_age=86400 * 365,
        path="/",
        samesite="lax",
    )
    return res


@router.get("/settings/export-data")
async def settings_export_data(
    current_user: User | None = Depends(get_authenticated_web_user),
    profile_service: ProfileService = Depends(get_profile_service),
    app_service: ApplicationService = Depends(get_application_service),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Exporta o dossiê completo em JSON (Direito à Portabilidade - LGPD Art. 18)."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    start_time = time.perf_counter()
    raw_dossier = await profile_service.get_full_dossier(current_user.id)
    apps = await app_service.list_applications(current_user)

    stmt_resumes = select(GeneratedResume).where(GeneratedResume.user_id == current_user.id)
    res_resumes = await db.execute(stmt_resumes)
    resumes = res_resumes.scalars().all()

    export_payload = {
        "exported_at": datetime.now(UTC).isoformat(),
        "compliance": "LGPD Art. 18, II e V / GDPR Art. 20 (Direito a Portabilidade dos Dados)",
        "user_profile": {
            "id": str(current_user.id),
            "full_name": current_user.full_name,
            "email": current_user.email,
            "target_title": current_user.target_title,
            "location": current_user.location,
            "phone": current_user.phone,
            "linkedin_url": current_user.linkedin_url,
            "github_url": current_user.github_url,
            "portfolio_url": current_user.portfolio_url,
            "professional_summary": current_user.professional_summary,
        },
        "dossier": {
            "experiences": [
                {
                    "company_name": e.company_name,
                    "position_title": e.position_title,
                    "start_date": str(e.start_date) if e.start_date else None,
                    "end_date": str(e.end_date) if e.end_date else None,
                    "tech_stack": e.tech_stack,
                    "achievements": e.achievements,
                }
                for e in raw_dossier.get("experiences", [])
            ],
            "skills": [s.name for s in raw_dossier.get("skills", [])],
            "educations": [
                {
                    "institution_name": ed.institution_name,
                    "degree": ed.degree,
                    "field_of_study": ed.field_of_study,
                    "start_date": str(ed.start_date) if ed.start_date else None,
                    "end_date": str(ed.end_date) if ed.end_date else None,
                }
                for ed in raw_dossier.get("educations", [])
            ],
            "certifications": [
                {
                    "name": c.name,
                    "issuing_organization": c.issuing_organization,
                }
                for c in raw_dossier.get("certifications", [])
            ],
        },
        "applications": [
            {
                "id": str(a.id),
                "company_name": a.company_name,
                "job_title": a.job_title,
                "status": a.status,
                "applied_at": str(a.applied_at) if a.applied_at else None,
            }
            for a in apps
        ],
        "generated_resumes_count": len(resumes),
    }

    json_bytes = json.dumps(export_payload, indent=2, ensure_ascii=False).encode("utf-8")
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    logger.info(
        "web_user_data_exported",
        user_id=str(current_user.id),
        duration_ms=duration_ms,
    )

    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="thothcvs_meus_dados.json"'},
    )


@router.post("/settings/delete-account")
async def settings_delete_account(
    request: Request,
    current_user: User | None = Depends(get_authenticated_web_user),
    user_service: UserService = Depends(get_user_service),
) -> Response:
    """Elimina permanentemente a conta e dados do usuário (LGPD Art. 18, VI)."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    start_time = time.perf_counter()
    user_id_str = str(current_user.id)
    await user_service.delete_user_account(current_user)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    logger.info(
        "web_user_account_deleted",
        user_id=user_id_str,
        duration_ms=duration_ms,
    )

    response = Response(
        status_code=status.HTTP_200_OK,
        headers={"HX-Redirect": "/?msg=account_deleted"},
    )
    response.delete_cookie("session_token", path="/")
    return response
