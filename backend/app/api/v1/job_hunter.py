"""Rotas da API v1 para o Agente Autônomo 'Job Hunter'.

Disponibiliza endpoints de triagem autônoma de vagas, avaliação de aderência
ao dossiê e integração direta com o funil ATS pessoal.
"""

from fastapi import APIRouter, Depends, status

from app.api.v1.deps import get_current_user, get_job_hunter_service
from app.api.v1.schemas.job_hunter import JobHunterGoalConfig, JobHunterRunResponse
from app.core.logging import get_logger
from app.core.telemetry import set_user_id
from app.domain.models import User
from app.services.job_hunter_service import JobHunterService

logger = get_logger(__name__)

router = APIRouter(prefix="/job-hunter", tags=["Job Hunter Agent"])


@router.post(
    "/hunt",
    response_model=JobHunterRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Executa triagem e busca autônoma de vagas",
    description=(
        "Analisa um lote de URLs de vagas de emprego, extrai requisitos semânticos com IA, "
        "calcula aderência contra o Dossiê Mestre e opcionalmente pré-cadastra no funil ATS."
    ),
)
async def hunt_jobs(
    payload: JobHunterGoalConfig,
    current_user: User = Depends(get_current_user),
    service: JobHunterService = Depends(get_job_hunter_service),
) -> JobHunterRunResponse:
    """Dispara o pipeline de triagem autônoma de vagas para o usuário autenticado."""
    set_user_id(str(current_user.id))
    logger.info(
        "job_hunter_api_hunt_requested",
        user_id=str(current_user.id),
        sources_count=len(payload.source_urls),
        auto_pre_apply=payload.auto_pre_apply,
    )
    return await service.hunt_and_triage(user=current_user, goals=payload)
