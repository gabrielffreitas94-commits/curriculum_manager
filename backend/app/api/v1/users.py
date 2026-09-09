"""Endpoints de gestão de perfil e preferências do usuário logado."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.api.v1.schemas.user import UserSettingsResponse, UserSettingsUpdateRequest
from app.core.crypto import crypto_service
from app.core.database import get_db_session
from app.domain.models import User, UserSettings

router = APIRouter(prefix="/users", tags=["Usuários e Configurações"])


@router.get(
    "/me/settings",
    response_model=UserSettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta configurações do usuário logado",
    description="Retorna as preferências ativas e se há chave da API Gemini configurada.",
)
async def get_my_settings(
    current_user: User = Depends(get_current_user),
) -> UserSettingsResponse:
    """Retorna as configurações do usuário autenticado sem expor a API key real.

    Args:
        current_user: Usuário autenticado obtido pela dependência injetada.

    Returns:
        UserSettingsResponse: Objeto com as preferências do usuário.
    """
    settings: UserSettings | None = current_user.settings
    has_key = bool(settings and settings.encrypted_gemini_api_key)

    return UserSettingsResponse(
        preferred_language=settings.preferred_language if settings else "pt-BR",
        has_gemini_key=has_key,
        email_notifications_enabled=(
            settings.email_notifications_enabled if settings else True
        ),
        in_app_notifications_enabled=(
            settings.in_app_notifications_enabled if settings else True
        ),
        default_prompt_skill_id=(
            settings.default_prompt_skill_id if settings else None
        ),
    )


@router.put(
    "/me/settings",
    response_model=UserSettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="Atualiza preferências e chave do Gemini",
    description="Atualiza configurações do usuário e cifra a API key do Gemini com AES-GCM-256.",
)
async def update_my_settings(
    body: UserSettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserSettingsResponse:
    """Atualiza as preferências do usuário protegendo a chave de API em repouso.

    Args:
        body: Payload contendo campos modificados e opcionalmente a nova API Key.
        current_user: Usuário ativo autenticado.
        db: Sessão de banco de dados assíncrona.

    Returns:
        UserSettingsResponse: Configurações atualizadas confirmadas.
    """
    settings: UserSettings | None = current_user.settings
    if settings is None:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
        await db.flush()
        current_user.settings = settings

    if body.gemini_api_key is not None:
        if body.gemini_api_key.strip():
            # Cifra a chave antes de persistir no banco relacional
            settings.encrypted_gemini_api_key = crypto_service.encrypt(
                body.gemini_api_key.strip()
            )
        else:
            settings.encrypted_gemini_api_key = None

    if body.preferred_language is not None:
        settings.preferred_language = body.preferred_language

    if body.email_notifications_enabled is not None:
        settings.email_notifications_enabled = body.email_notifications_enabled

    if body.in_app_notifications_enabled is not None:
        settings.in_app_notifications_enabled = body.in_app_notifications_enabled

    if body.default_prompt_skill_id is not None:
        settings.default_prompt_skill_id = body.default_prompt_skill_id

    has_key = bool(settings.encrypted_gemini_api_key)

    return UserSettingsResponse(
        preferred_language=settings.preferred_language,
        has_gemini_key=has_key,
        email_notifications_enabled=settings.email_notifications_enabled,
        in_app_notifications_enabled=settings.in_app_notifications_enabled,
        default_prompt_skill_id=settings.default_prompt_skill_id,
    )
