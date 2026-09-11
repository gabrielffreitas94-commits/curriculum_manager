"""Rotas da API para notificações in-app e alertas do ATS."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.api.v1.schemas.notification import (
    BatchUpdateResponse,
    NotificationResponse,
    ScanFollowUpsResponse,
    UnreadCountResponse,
)
from app.core.database import get_db_session
from app.domain.models import User
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notificações e Lembretes"])


def get_notification_service(
    db: AsyncSession = Depends(get_db_session),
) -> NotificationService:
    """Injeta o serviço de notificações com a sessão transacional do banco."""
    return NotificationService(db=db)


@router.get(
    "",
    response_model=list[NotificationResponse],
    summary="Lista notificações do usuário",
)
async def list_notifications(
    unread_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Any:
    return await service.list_notifications(user=current_user, unread_only=unread_only)


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Contagem de notificações não lidas",
)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Any:
    count = await service.get_unread_count(user=current_user)
    return UnreadCountResponse(unread_count=count)


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Marca notificação como lida",
)
async def mark_as_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Any:
    return await service.mark_as_read(user=current_user, notification_id=notification_id)


@router.post(
    "/mark-all-read",
    response_model=BatchUpdateResponse,
    summary="Marca todas as notificações como lidas",
)
async def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Any:
    updated = await service.mark_all_as_read(user=current_user)
    return BatchUpdateResponse(updated_count=updated)


@router.post(
    "/scan-follow-ups",
    response_model=ScanFollowUpsResponse,
    summary="Dispara varredura proativa de follow-ups",
    description="Gera notificações automáticas para vagas sem resposta há mais de 7 dias.",
)
async def scan_follow_ups(
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> Any:
    created = await service.scan_and_generate_follow_ups(user=current_user)
    return ScanFollowUpsResponse(created_count=created)
