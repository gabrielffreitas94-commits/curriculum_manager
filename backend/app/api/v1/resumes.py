"""Rotas da API para análise de oportunidades e síntese inteligente de currículos."""

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.api.v1.schemas.resume import (
    JobAnalyzeRequest,
    ResumeGenerateRequest,
    ResumeGenerateResponse,
)
from app.core.database import get_db_session
from app.domain.models import User
from app.ports.ai_port import JobAnalysisResult
from app.services.resume_service import ResumeService

router = APIRouter(prefix="/resumes", tags=["Motor de Inteligência e Currículos"])


def get_resume_service(db: AsyncSession = Depends(get_db_session)) -> ResumeService:
    """Injeta a instância do serviço de currículos com a sessão ativa de banco de dados."""
    return ResumeService(db=db)


@router.post(
    "/analyze-job",
    response_model=JobAnalysisResult,
    status_code=status.HTTP_200_OK,
    summary="Extrai requisitos semânticos da vaga com IA",
    description=(
        "Decompõe o anúncio da oportunidade em competências mandatórias, "
        "desejáveis e palavras-chave ATS."
    ),
)
async def analyze_job(
    body: JobAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    service: ResumeService = Depends(get_resume_service),
) -> Any:
    return await service.analyze_job(
        user=current_user, job_description=body.job_description
    )


@router.post(
    "/generate",
    response_model=ResumeGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Gera currículo inteligente e estruturado",
    description=(
        "Executa o pipeline completo de 4 estágios: análise, injeção factual restritiva, "
        "geração estruturada e auditoria algorítmica anti-alucinação."
    ),
)
async def generate_resume(
    body: ResumeGenerateRequest,
    current_user: User = Depends(get_current_user),
    service: ResumeService = Depends(get_resume_service),
) -> Any:
    return await service.generate_resume(user=current_user, payload=body)
