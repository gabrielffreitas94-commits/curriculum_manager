import hmac
import html
import json
import secrets
from pathlib import Path

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
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import (
    create_copilot_service,
    get_auth_service,
    get_job_ingest_service,
    get_profile_service,
    get_prompt_skill_service,
    get_resume_parser_adapter,
    get_resume_service,
    google_oauth_adapter,
    resolve_gemini_api_key,
)
from app.api.v1.schemas.resume import ResumeGenerateRequest
from app.core.config import settings
from app.core.database import get_db_session
from app.core.file_security import FileSecurityError, validate_resume_file
from app.core.logging import get_logger
from app.core.telemetry import set_user_id
from app.core.url_scraper import URLScraperError
from app.domain.models import User
from app.ports.ai_port import ChatMessage
from app.ports.oauth_port import OAuthError
from app.ports.resume_parser_port import ParsedProfileDTO, ResumeParserError
from app.services.auth_service import AuthService
from app.services.job_ingest_service import JobIngestService
from app.services.profile_service import ProfileService
from app.services.prompt_skill_service import PromptSkillService
from app.services.resume_service import ResumeService

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
async def scrape_job_url(
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
async def upload_job_doc(
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
async def generate_custom_resume(
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
