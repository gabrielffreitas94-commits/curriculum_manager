"""Rotas da API para análise de oportunidades, síntese e exportação de currículos."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_document_service
from app.api.v1.schemas.resume import (
    JobAnalyzeRequest,
    MatchPreviewRequest,
    MatchPreviewResponse,
    ResumeGenerateRequest,
    ResumeGenerateResponse,
)
from app.core.database import get_db_session
from app.domain.models import User
from app.ports.ai_port import JobAnalysisResult
from app.services.document_service import DocumentService
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
    "/match-preview",
    response_model=MatchPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Avalia fit e aderência semântica contra a vaga",
    description="Calcula a pontuação de match e sugere palavras-chave antes de gerar o currículo.",
)
async def match_preview(
    body: MatchPreviewRequest,
    current_user: User = Depends(get_current_user),
    service: ResumeService = Depends(get_resume_service),
) -> Any:
    return await service.match_preview(
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


@router.get(
    "/{resume_id}/export/pdf",
    summary="Exporta currículo gerado no formato PDF",
    description="Renderiza o currículo em PDF vetorial de alta fidelidade com CSS paged media.",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Arquivo PDF gerado para download.",
        }
    },
)
async def export_resume_pdf(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> Response:
    """Exporta o currículo do usuário no formato PDF.

    Args:
        resume_id: Identificador universal do currículo gerado.
        current_user: Usuário autenticado proprietário.
        service: Serviço de renderização injetado.

    Returns:
        Response HTTP contendo o fluxo binário de bytes do PDF e headers para download.
    """
    pdf_bytes, filename = await service.export_pdf(
        resume_id=resume_id, user=current_user
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/{resume_id}/export/docx",
    summary="Exporta currículo gerado no formato Word (.docx)",
    description="Gera o currículo em formato OpenXML DOCX com diagramação otimizada para ATS.",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {}
            },
            "description": "Arquivo DOCX gerado para download.",
        }
    },
)
async def export_resume_docx(
    resume_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> Response:
    """Exporta o currículo do usuário no formato Word (.docx).

    Args:
        resume_id: Identificador universal do currículo gerado.
        current_user: Usuário autenticado proprietário.
        service: Serviço de renderização injetado.

    Returns:
        Response HTTP contendo o binário DOCX e headers de anexo para download.
    """
    docx_bytes, filename = await service.export_docx(
        resume_id=resume_id, user=current_user
    )
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return Response(
        content=docx_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

