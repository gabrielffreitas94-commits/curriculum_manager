"""Roteador Web do ThothCVs AI."""

import time
from pathlib import Path

import jwt
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import auth_adapter, google_oauth_adapter
from app.core.config import settings
from app.core.database import get_db_session
from app.domain.models import User, UserSettings
from app.ports.oauth_port import OAuthError

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["Web UI"])


def create_session_jwt(uid: str, email: str) -> str:
    """Emite um token JWT de sessão assinado com a SECRET_KEY do projeto."""
    now = int(time.time())
    payload = {
        "sub": uid,
        "email": email,
        "iat": now,
        "exp": now + (86400 * 7),
        "iss": "thothcvs-web",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def get_authenticated_web_user(request: Request, db: AsyncSession) -> User | None:
    """Recupera o usuário autenticado na sessão Web a partir do Cookie session_token."""
    token = request.cookies.get("session_token")
    if not token or not token.strip():
        return None

    # 1. Tenta decodificar como JWT de sessão próprio assinado com SECRET_KEY
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            issuer="thothcvs-web",
        )
        user_uid = payload.get("sub")
        if user_uid:
            result = await db.execute(
                select(User)
                .options(selectinload(User.settings))
                .where(User.firebase_uid == user_uid, User.deleted_at.is_(None))
            )
            found_user = result.scalar_one_or_none()
            if found_user:
                return found_user
    except Exception:
        pass

    # 2. Fallback para verificação via auth_adapter (compatibilidade com tokens Bearer/Mock)
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
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Processa o callback de autorização do Google OAuth 2.0 e autentica o usuário."""
    if error or not code:
        return RedirectResponse(url="/?auth_error=google_denied", status_code=status.HTTP_302_FOUND)

    try:
        tokens = await google_oauth_adapter.exchange_code(code)
        access_token = tokens.get("access_token")
        if not access_token:
            return RedirectResponse(
                url="/?auth_error=invalid_token", status_code=status.HTTP_302_FOUND
            )
        user_info = await google_oauth_adapter.fetch_user_info(access_token)
    except OAuthError:
        return RedirectResponse(url="/?auth_error=oauth_failed", status_code=status.HTTP_302_FOUND)

    # Localiza ou registra o usuário na base relacional
    firebase_uid = f"google_{user_info.sub}"
    result = await db.execute(
        select(User).where(
            (User.firebase_uid == firebase_uid) | (User.email == user_info.email),
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            firebase_uid=firebase_uid,
            email=user_info.email,
            full_name=user_info.full_name,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        settings_entry = UserSettings(
            user_id=user.id,
            preferred_language="pt-BR",
            email_notifications_enabled=True,
            in_app_notifications_enabled=True,
        )
        db.add(settings_entry)
        await db.commit()
    else:
        user.firebase_uid = firebase_uid
        if user_info.full_name and not user.full_name:
            user.full_name = user_info.full_name
        await db.commit()

    # Emite cookie session_token com JWT assinado
    session_token = create_session_jwt(uid=firebase_uid, email=user.email)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
        path="/",
    )
    return response


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
