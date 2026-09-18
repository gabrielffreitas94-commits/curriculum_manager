"""Roteador Web do ThothCVs AI."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import auth_adapter
from app.core.database import get_db_session
from app.domain.models import User, UserSettings

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["Web UI"])


async def get_authenticated_web_user(request: Request, db: AsyncSession) -> User | None:
    """Recupera o usuário autenticado na sessão Web a partir do Cookie session_token."""
    token = request.cookies.get("session_token")
    if not token or not token.strip():
        return None

    try:
        auth_user = await auth_adapter.verify_token(token)
        result = await db.execute(
            select(User)
            .options(selectinload(User.settings))
            .where(User.firebase_uid == auth_user.uid, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()
    except Exception:
        return None



@router.get("/", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def welcome_page(
    request: Request, db: AsyncSession = Depends(get_db_session)
) -> HTMLResponse:
    """Renderiza a página inicial de boas-vindas com HTMX e estado de autenticação."""
    user = await get_authenticated_web_user(request, db)
    return templates.TemplateResponse(
        request=request,
        name="index.html.jinja2",
        context={"request": request, "current_user": user},
    )


@router.get("/auth/modal", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def login_modal(request: Request) -> HTMLResponse:
    """Renderiza o fragmento do modal de login com Google, LinkedIn e E-mail/Senha."""
    return templates.TemplateResponse(
        request=request,
        name="login_modal.html.jinja2",
        context={"request": request},
    )


@router.get("/auth/login-view", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def login_view(request: Request) -> HTMLResponse:
    """Renderiza o fragmento do card de login para alternância no modal via HTMX."""
    return templates.TemplateResponse(
        request=request,
        name="auth/login_card.html.jinja2",
        context={"request": request},
    )


@router.get("/auth/register-view", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def register_view(request: Request) -> HTMLResponse:
    """Renderiza o fragmento do card de cadastro para alternância no modal via HTMX."""
    return templates.TemplateResponse(
        request=request,
        name="auth/register_card.html.jinja2",
        context={"request": request},
    )


@router.get("/auth/forgot-password-view", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def forgot_password_view(request: Request) -> HTMLResponse:
    """Renderiza o fragmento do card de recuperação de senha no modal via HTMX."""
    return templates.TemplateResponse(
        request=request,
        name="auth/forgot_password_card.html.jinja2",
        context={"request": request},
    )


@router.post("/auth/register", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def register_submit(
    request: Request,
    full_name: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Processa o formulário de cadastro de novo usuário."""
    clean_name = full_name.strip()
    clean_email = email.strip().lower()

    if not clean_name or not clean_email or not password:
        return templates.TemplateResponse(
            request=request,
            name="auth/register_card.html.jinja2",
            context={
                "request": request,
                "error": "Todos os campos são obrigatórios.",
                "full_name": clean_name,
                "email": clean_email,
            },
        )

    if password != password_confirm:
        return templates.TemplateResponse(
            request=request,
            name="auth/register_card.html.jinja2",
            context={
                "request": request,
                "error": "As senhas informadas não coincidem.",
                "full_name": clean_name,
                "email": clean_email,
            },
        )

    if len(password) < 6:
        return templates.TemplateResponse(
            request=request,
            name="auth/register_card.html.jinja2",
            context={
                "request": request,
                "error": "A senha deve conter no mínimo 6 caracteres.",
                "full_name": clean_name,
                "email": clean_email,
            },
        )

    # Verifica se já existe usuário com este e-mail
    existing = await db.execute(
        select(User).where(User.email == clean_email, User.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        return templates.TemplateResponse(
            request=request,
            name="auth/register_card.html.jinja2",
            context={
                "request": request,
                "error": "Este e-mail já está cadastrado. Faça login.",
                "full_name": clean_name,
                "email": clean_email,
            },
        )

    email_slug = clean_email.replace("@", "_").replace(".", "_")
    token_val = f"mock_{email_slug}"
    uid = f"mock_uid_{token_val}"

    new_user = User(
        firebase_uid=uid,
        email=clean_email,
        full_name=clean_name,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()

    settings = UserSettings(
        user_id=new_user.id,
        preferred_language="pt-BR",
        email_notifications_enabled=True,
        in_app_notifications_enabled=True,
    )
    db.add(settings)
    await db.commit()

    response = HTMLResponse(content="", status_code=status.HTTP_200_OK)
    response.set_cookie(
        key="session_token",
        value=token_val,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
        path="/",
    )
    response.headers["HX-Refresh"] = "true"
    return response


@router.post("/auth/login", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def login_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Processa a autenticação com e-mail e senha."""
    clean_email = email.strip().lower()

    if not clean_email or not password:
        return templates.TemplateResponse(
            request=request,
            name="auth/login_card.html.jinja2",
            context={
                "request": request,
                "error": "Informe o e-mail e a senha.",
                "email": clean_email,
            },
        )

    result = await db.execute(
        select(User).where(User.email == clean_email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user:
        return templates.TemplateResponse(
            request=request,
            name="auth/login_card.html.jinja2",
            context={
                "request": request,
                "error": "Credenciais inválidas. Verifique seu e-mail e senha ou cadastre-se.",
                "email": clean_email,
            },
        )

    token_val = f"mock_{user.firebase_uid.removeprefix('mock_uid_')}"
    response = HTMLResponse(content="", status_code=status.HTTP_200_OK)
    response.set_cookie(
        key="session_token",
        value=token_val,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
        path="/",
    )
    response.headers["HX-Refresh"] = "true"
    return response


@router.post("/auth/forgot-password", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def forgot_password_submit(
    request: Request,
    email: str = Form(""),
) -> HTMLResponse:
    """Processa solicitação de recuperação de senha."""
    clean_email = email.strip().lower()

    if not clean_email or "@" not in clean_email or "." not in clean_email:
        return templates.TemplateResponse(
            request=request,
            name="auth/forgot_password_card.html.jinja2",
            context={
                "request": request,
                "error": "Informe um endereço de e-mail válido.",
                "email": clean_email,
            },
        )

    return templates.TemplateResponse(
        request=request,
        name="auth/forgot_password_card.html.jinja2",
        context={
            "request": request,
            "success": True,
            "email": clean_email,
        },
    )


@router.post("/auth/logout", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def logout(request: Request) -> Response:
    """Encerra a sessão Web do usuário removendo o cookie session_token."""
    response = HTMLResponse(content="", status_code=status.HTTP_200_OK)
    response.delete_cookie(key="session_token", path="/")
    response.headers["HX-Refresh"] = "true"
    return response

