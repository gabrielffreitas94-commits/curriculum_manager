"""Roteador Web do ThothCVs AI."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response, status
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


@router.post("/auth/login/google", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def login_google(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Realiza autenticação via conta Google."""
    token_val = "mock_google_user"
    mock_uid = f"mock_uid_{token_val}"
    email = "usuario.google@exemplo.com"
    full_name = "Usuário Google"

    result = await db.execute(
        select(User).where(User.firebase_uid == mock_uid, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            firebase_uid=mock_uid,
            email=email,
            full_name=full_name,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        settings = UserSettings(
            user_id=user.id,
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


@router.post("/auth/login/linkedin", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def login_linkedin(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Realiza autenticação via conta LinkedIn."""
    token_val = "mock_linkedin_user"
    mock_uid = f"mock_uid_{token_val}"
    email = "usuario.linkedin@exemplo.com"
    full_name = "Usuário LinkedIn"

    result = await db.execute(
        select(User).where(User.firebase_uid == mock_uid, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            firebase_uid=mock_uid,
            email=email,
            full_name=full_name,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        settings = UserSettings(
            user_id=user.id,
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


@router.post("/auth/logout", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def logout(request: Request) -> Response:
    """Encerra a sessão Web do usuário removendo o cookie session_token."""
    response = HTMLResponse(content="", status_code=status.HTTP_200_OK)
    response.delete_cookie(key="session_token", path="/")
    response.headers["HX-Refresh"] = "true"
    return response


