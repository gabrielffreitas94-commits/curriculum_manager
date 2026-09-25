"""Rotas da API para análise de oportunidades, síntese e exportação de currículos."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import (
    get_copilot_service,
    get_current_user,
    get_document_service,
    get_job_ingest_service,
    get_prompt_skill_service,
)
from app.api.v1.schemas.resume import (
    CopilotChatRequest,
    CopilotChatResponse,
    JobAnalyzeRequest,
    JobIngestResponse,
    JobUrlIngestRequest,
    MatchPreviewRequest,
    MatchPreviewResponse,
    PromptSkillResponse,
    ResumeGenerateRequest,
    ResumeGenerateResponse,
)
from app.core.config import settings
from app.core.database import get_db_session
from app.core.rate_limit import limiter
from app.domain.models import User
from app.ports.ai_port import ChatMessage, JobAnalysisResult
from app.services.copilot_service import CopilotService
from app.services.document_service import DocumentService
from app.services.job_ingest_service import JobIngestService
from app.services.prompt_skill_service import PromptSkillService
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
@limiter.limit(settings.RATE_LIMIT_ANALYZE_JOB)
async def analyze_job(
    request: Request,
    body: JobAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    service: ResumeService = Depends(get_resume_service),
) -> Any:
    return await service.analyze_job(user=current_user, job_description=body.job_description)


@router.post(
    "/match-preview",
    response_model=MatchPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Avalia fit e aderência semântica contra a vaga",
    description="Calcula a pontuação de match e sugere palavras-chave antes de gerar o currículo.",
)
@limiter.limit(settings.RATE_LIMIT_MATCH_PREVIEW)
async def match_preview(
    request: Request,
    body: MatchPreviewRequest,
    current_user: User = Depends(get_current_user),
    service: ResumeService = Depends(get_resume_service),
) -> Any:
    return await service.match_preview(user=current_user, job_description=body.job_description)


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
@limiter.limit(settings.RATE_LIMIT_GENERATE)
async def generate_resume(
    request: Request,
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
    pdf_bytes, filename = await service.export_pdf(resume_id=resume_id, user=current_user)
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
    docx_bytes, filename = await service.export_docx(resume_id=resume_id, user=current_user)
    media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(
        content=docx_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/prompt-skills",
    response_model=list[PromptSkillResponse],
    status_code=status.HTTP_200_OK,
    summary="Lista metodologias e personas de confecção de currículo",
    description=(
        "Retorna as metodologias padrão de mercado (Google XYZ, STAR, Startup, Enterprise, "
        "Executive) e personas customizadas do usuário."
    ),
)
async def list_prompt_skills(
    current_user: User = Depends(get_current_user),
    service: PromptSkillService = Depends(get_prompt_skill_service),
) -> Any:
    skills = await service.list_active_skills(user_id=current_user.id)
    return [
        PromptSkillResponse(
            id=s.id,
            slug=s.slug,
            name=s.name,
            description=s.description,
            category=s.category,
            system_prompt=s.system_prompt,
            default_language=s.default_language,
            is_system_default=s.is_system_default,
        )
        for s in skills
    ]


@router.post(
    "/ingest/url",
    response_model=JobIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Extrai descrição da vaga a partir de URL pública",
    description="Efetua scraping seguro com blindagem anti-SSRF (CWE-918) e limite de tamanho.",
)
async def ingest_job_from_url(
    body: JobUrlIngestRequest,
    current_user: User = Depends(get_current_user),
    service: JobIngestService = Depends(get_job_ingest_service),
) -> Any:
    text = await service.extract_text_from_url(url=body.url)
    return JobIngestResponse(job_description=text, source_type="url", char_count=len(text))


@router.post(
    "/ingest/document",
    response_model=JobIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Extrai descrição da vaga a partir de upload de documento (PDF/DOCX)",
    description="Valida magic bytes (CWE-434), limite de 5 MB (CWE-400) e extrai o texto.",
)
async def ingest_job_from_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    service: JobIngestService = Depends(get_job_ingest_service),
) -> Any:
    content = await file.read()
    filename = file.filename or "vaga.pdf"
    text = service.extract_text_from_document(file_bytes=content, filename=filename)
    return JobIngestResponse(job_description=text, source_type="document", char_count=len(text))


@router.post(
    "/copilot/chat",
    response_model=CopilotChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Conversa interativa com o Copilot de IA para tailoring de currículo",
    description=(
        "Troca mensagens consultivas orientadas pela vaga, metodologia escolhida e "
        "dossiê factual real do candidato."
    ),
)
async def copilot_chat(
    body: CopilotChatRequest,
    current_user: User = Depends(get_current_user),
    service: CopilotService = Depends(get_copilot_service),
) -> Any:
    messages = [ChatMessage(role=m.role, content=m.content) for m in body.messages]
    reply = await service.chat(
        user=current_user,
        job_description=body.job_description,
        prompt_skill_slug=body.prompt_skill_slug,
        messages=messages,
    )
    return CopilotChatResponse(reply=reply)
