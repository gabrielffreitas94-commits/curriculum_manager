import hmac
import html
import json
import secrets
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from fastapi.responses import HTMLResponse, RedirectResponse
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
from app.domain.models import Application, GeneratedResume, User, UserSettings
from app.ports.ai_port import ChatMessage
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


# ==================== GERADOR DE CURRÍCULO & TAILORING (WEB UI) ====================
@router.get("/resumes/new", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def new_resume_page(
    request: Request,
    current_user: User | None = Depends(get_authenticated_web_user),
    prompt_skill_service: PromptSkillService = Depends(get_prompt_skill_service),
) -> Response:
    """Renderiza a página interativa de criação e tailoring de currículo sob medida."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    skills = await prompt_skill_service.list_active_skills(user_id=current_user.id)
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
    except Exception as exc:
        logger.error("web_copilot_chat_error", error=str(exc), exc_info=True)
        error_msg = f"Falha ao comunicar com o assistente de IA: {exc}"

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
    current_user: User | None = Depends(get_authenticated_web_user),
    resume_service: ResumeService = Depends(get_resume_service),
) -> Response:
    """Dispara a geração de currículo inteligente e estruturado a partir da interface web."""
    if current_user is None:
        return RedirectResponse(
            url="/?auth_error=login_required", status_code=status.HTTP_302_FOUND
        )

    result = await resume_service.generate_resume(
        user=current_user,
        payload=ResumeGenerateRequest(
            job_description=job_description,
            prompt_skill_slug=prompt_skill_slug,
        ),
    )
    logger.info(
        "web_custom_resume_generated",
        user_id=str(current_user.id),
        resume_id=str(result.resume_id),
    )
    return RedirectResponse(
        url=f"/resumes/{result.resume_id}/preview", status_code=status.HTTP_302_FOUND
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
                    "tech_stack": base_exp.get("tech_stack", []),
                    "bullet_points": bullet_points,
                    "achievements": bullet_points,
                }
            )
        content["selected_experiences"] = updated_exps
        content["experiences"] = updated_exps

    return content


@router.get("/resumes/{resume_id}/preview", response_class=HTMLResponse)
async def resume_preview_page(
    request: Request,
    resume_id: uuid.UUID,
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Carrega o editor Live Split-View com pré-visualização A4 sincronizada."""
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

    stmt_app = select(Application).where(Application.id == resume.application_id)
    res_app = await db.execute(stmt_app)
    application = res_app.scalar_one_or_none()

    return templates.TemplateResponse(
        request=request,
        name="resumes/preview.html.jinja2",
        context={
            "request": request,
            "resume": resume,
            "application": application,
            "content": resume.structured_content,
            "current_user": current_user,
            "active_tab": "resumes",
        },
    )


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
    gemini_api_key: str = Form(...),
    current_user: User | None = Depends(get_authenticated_web_user),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Cifra via AES-GCM-256 com AAD e persiste a chave pessoal do Gemini."""
    if current_user is None:
        return HTMLResponse(
            content="<script>window.location.href='/?auth_error=login_required';</script>",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    clean_key = gemini_api_key.strip()
    if not clean_key:
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
    encrypted_key = crypto_service.encrypt(clean_key, associated_data=user_aad)

    stmt = select(UserSettings).where(UserSettings.user_id == current_user.id)
    result = await db.execute(stmt)
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        user_settings = UserSettings(
            user_id=current_user.id,
            encrypted_gemini_api_key=encrypted_key,
        )
        db.add(user_settings)
    else:
        user_settings.encrypted_gemini_api_key = encrypted_key
        user_settings.updated_at = datetime.now(UTC)

    await db.commit()

    logger.info(
        "web_gemini_key_saved",
        user_id=str(current_user.id),
    )

    success_html = (
        '<div class="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 '
        "border border-emerald-200 dark:border-emerald-800 text-xs font-semibold "
        "text-emerald-800 dark:text-emerald-300 flex items-center justify-between "
        'animate-in fade-in">\n'
        "  <span>✅ Chave do Google Gemini salva e cifrada com sucesso "
        "(AES-GCM-256 com AAD)!</span>\n"
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
        adapter = GeminiAIAdapter(api_key=key_to_test)
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
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(
            "web_gemini_key_test_failed",
            user_id=str(current_user.id),
            error=str(exc),
            duration_ms=duration_ms,
            exc_info=True,
        )
        escaped_err = html.escape(str(exc))
        fail_html = (
            f'<div class="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/60 '
            f"border border-rose-200 dark:border-rose-800 text-xs font-semibold "
            f"text-rose-800 dark:text-rose-300 flex items-center justify-between "
            f'animate-in fade-in">\n'
            f"  <span>❌ Falha ao validar a chave com o Google AI Studio: {escaped_err}</span>\n"
            f'  <button type="button" onclick="this.parentElement.remove()" '
            f'class="text-rose-600 dark:text-rose-400 hover:opacity-80 cursor-pointer">✕</button>\n'
            f"</div>"
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
