"""Endpoints de autenticação, sincronização de perfil e gestão de sessão."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_current_auth_user
from app.api.v1.schemas.user import UserResponse, UserSettingsResponse, UserSyncRequest
from app.core.database import get_db_session
from app.domain.models import User, UserSettings
from app.ports.auth_port import AuthUser

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post(
    "/sync",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincroniza o usuário pós-login com Firebase",
    description=(
        "Endpoint idempotente chamado logo após o login no frontend com Firebase Auth. "
        "Se o usuário já existir no banco relacional, atualiza os dados cadastrais básicos. "
        "Se for o primeiro acesso, cria a conta e inicializa as preferências do usuário."
    ),
)
async def sync_user(
    body: UserSyncRequest | None = None,
    auth_user: AuthUser = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Sincroniza a identidade autenticada no Firebase com o PostgreSQL.

    Args:
        body: Dados cadastrais complementares opcionais enviados pelo cliente.
        auth_user: Dados do usuário autenticado validados no token Bearer.
        db: Sessão assíncrona com o banco de dados.

    Returns:
        UserResponse: Modelo serializado do usuário com configurações ativas.
    """
    payload = body or UserSyncRequest()

    # Busca usuário ativo existente pelo UID Firebase
    result = await db.execute(
        select(User)
        .options(selectinload(User.settings))
        .where(User.firebase_uid == auth_user.uid, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Primeiro login do usuário: cria entidade de usuário e preferências padrão
        user = User(
            firebase_uid=auth_user.uid,
            email=auth_user.email,
            full_name=auth_user.full_name,
            target_title=payload.target_title,
            phone=payload.phone,
            location=payload.location,
        )
        db.add(user)
        await db.flush()

        settings = UserSettings(
            user_id=user.id,
            preferred_language=payload.preferred_language or "pt-BR",
        )
        db.add(settings)
        await db.flush()
        user.settings = settings
    else:
        # Usuário recorrente: sincroniza eventuais mudanças
        if auth_user.full_name:
            user.full_name = auth_user.full_name
        if payload.target_title is not None:
            user.target_title = payload.target_title
        if payload.phone is not None:
            user.phone = payload.phone
        if payload.location is not None:
            user.location = payload.location

        if user.settings is None:
            settings = UserSettings(
                user_id=user.id,
                preferred_language=payload.preferred_language or "pt-BR",
            )
            db.add(settings)
            await db.flush()
            user.settings = settings

    has_key = bool(
        user.settings.encrypted_gemini_api_key and user.settings.encrypted_gemini_api_key.strip()
    )

    settings_resp = UserSettingsResponse(
        preferred_language=user.settings.preferred_language,
        has_gemini_key=has_key,
        email_notifications_enabled=user.settings.email_notifications_enabled,
        in_app_notifications_enabled=user.settings.in_app_notifications_enabled,
        default_prompt_skill_id=user.settings.default_prompt_skill_id,
    )

    return UserResponse(
        id=user.id,
        firebase_uid=user.firebase_uid,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        location=user.location,
        target_title=user.target_title,
        is_active=user.is_active,
        settings=settings_resp,
    )
