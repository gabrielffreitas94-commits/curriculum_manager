"""Rotas da API para ATS Pessoal e gestão do ciclo de vida de candidaturas."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.api.v1.schemas.application import (
    ApplicationAnalyticsMetrics,
    ApplicationContactCreate,
    ApplicationContactResponse,
    ApplicationCreate,
    ApplicationDetailResponse,
    ApplicationListItemResponse,
    ApplicationNoteCreate,
    ApplicationNoteResponse,
    ApplicationStageCreate,
    ApplicationStageResponse,
    ApplicationStageUpdate,
    ApplicationUpdate,
)
from app.core.database import get_db_session
from app.domain.models import User
from app.services.application_service import ApplicationService

router = APIRouter(prefix="/applications", tags=["ATS Pessoal e Candidaturas"])


def get_application_service(
    db: AsyncSession = Depends(get_db_session),
) -> ApplicationService:
    """Injeta a instância do ApplicationService com a sessão ativa de banco."""
    return ApplicationService(db=db)


@router.get(
    "",
    response_model=list[ApplicationListItemResponse],
    summary="Lista candidaturas do usuário",
    description="Retorna candidaturas ativas com filtros por status e pendência de follow-up.",
)
async def list_applications(
    status_filter: str | None = Query(default=None, alias="status"),
    needs_follow_up: bool | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> Any:
    return await service.list_applications(
        user=current_user,
        status_filter=status_filter,
        needs_follow_up=needs_follow_up,
    )


@router.post(
    "",
    response_model=ApplicationListItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra nova candidatura",
)
async def create_application(
    body: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> Any:
    return await service.create_application(user=current_user, payload=body)


@router.get(
    "/analytics/metrics",
    response_model=ApplicationAnalyticsMetrics,
    summary="Métricas de conversão do ATS",
    description="Calcula taxas de conversão para entrevista, propostas e alertas de follow-up.",
)
async def get_analytics_metrics(
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> Any:
    return await service.get_analytics_metrics(user=current_user)


@router.get(
    "/{app_id}",
    response_model=ApplicationDetailResponse,
    summary="Obtém detalhes da candidatura",
    description="Retorna dossiê da vaga incluindo etapas, contatos e notas.",
)
async def get_application_detail(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> Any:
    return await service.get_application_detail(user=current_user, app_id=app_id)


@router.patch(
    "/{app_id}",
    response_model=ApplicationListItemResponse,
    summary="Atualiza metadados da candidatura",
)
async def update_application(
    app_id: uuid.UUID,
    body: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> Any:
    return await service.update_application(user=current_user, app_id=app_id, payload=body)


@router.delete(
    "/{app_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove candidatura (soft delete)",
)
async def delete_application(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> None:
    await service.delete_application(user=current_user, app_id=app_id)


@router.post(
    "/{app_id}/stages",
    response_model=ApplicationStageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona etapa seletiva",
)
async def add_stage(
    app_id: uuid.UUID,
    body: ApplicationStageCreate,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> Any:
    return await service.add_stage(user=current_user, app_id=app_id, payload=body)


@router.patch(
    "/{app_id}/stages/{stage_id}",
    response_model=ApplicationStageResponse,
    summary="Atualiza etapa seletiva",
)
async def update_stage(
    app_id: uuid.UUID,
    stage_id: uuid.UUID,
    body: ApplicationStageUpdate,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> Any:
    return await service.update_stage(
        user=current_user, app_id=app_id, stage_id=stage_id, payload=body
    )


@router.post(
    "/{app_id}/contacts",
    response_model=ApplicationContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registra contato de recrutamento",
)
async def add_contact(
    app_id: uuid.UUID,
    body: ApplicationContactCreate,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> Any:
    return await service.add_contact(user=current_user, app_id=app_id, payload=body)


@router.post(
    "/{app_id}/notes",
    response_model=ApplicationNoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona anotação cronológica",
)
async def add_note(
    app_id: uuid.UUID,
    body: ApplicationNoteCreate,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> Any:
    return await service.add_note(user=current_user, app_id=app_id, payload=body)
