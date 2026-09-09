"""Serviço central de geração inteligente de currículos com IA (Google Gemini).

Orquestra o pipeline em 4 estágios:
1. Decomposição semântica da vaga (gemini-1.5-flash)
2. Injeção restritiva do Grounding Context (fatos do banco relacional)
3. Síntese via Structured Outputs (FullGeneratedResumePayload)
4. Auditoria algorítmica determinística anti-alucinação (GroundingAuditEngine)
"""

import os
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gemini_ai_adapter import GeminiAIAdapter
from app.api.v1.schemas.resume import (
    MatchAnalysisItemSchema,
    MatchPreviewResponse,
    ResumeGenerateRequest,
    ResumeGenerateResponse,
)
from app.core.crypto import crypto_service
from app.core.grounding_audit import GroundingAuditEngine
from app.core.vector_match import VectorMatchEngine
from app.domain.models import Application, GeneratedResume, PromptSkill, User
from app.ports.ai_port import AIError, JobAnalysisResult, MissingApiKeyError
from app.services.profile_service import ProfileService

# Trava global em memória para evitar requisições concorrentes da mesma conta
_ACTIVE_GENERATIONS: set[uuid.UUID] = set()


class ResumeService:
    """Orquestrador do ciclo de vida e geração de currículos por oportunidade.

    Attributes:
        _db: Sessão ativa assíncrona do SQLAlchemy.
        _audit_engine: Instância do motor de validação factual anti-alucinação.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o serviço com a sessão do banco relacional."""
        self._db = db
        self._audit_engine = GroundingAuditEngine()

    def _resolve_gemini_adapter(self, user: User) -> GeminiAIAdapter:
        """Obtém a chave da API do usuário (BYOK) decifrada ou fallback do ambiente.

        Args:
            user: Usuário autenticado.

        Returns:
            GeminiAIAdapter: Adaptador de IA instanciado com a chave correspondente.

        Raises:
            HTTPException: Status 400 se nenhuma chave de API for localizada.
        """
        api_key: str | None = None

        if user.settings and user.settings.encrypted_gemini_api_key:
            try:
                api_key = crypto_service.decrypt(user.settings.encrypted_gemini_api_key)
            except Exception:
                api_key = None

        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chave de API do Gemini não configurada. "
                "Cadastre sua chave pessoal (BYOK) nas configurações de conta.",
            )

        return GeminiAIAdapter(api_key=api_key)

    async def analyze_job(self, user: User, job_description: str) -> JobAnalysisResult:
        """Executa o Estágio 1 do pipeline analisando semanticamente a vaga.

        Args:
            user: Usuário solicitante.
            job_description: Texto da vaga.

        Returns:
            JobAnalysisResult: Requisitos mandatórios e termos ATS.
        """
        adapter = self._resolve_gemini_adapter(user)
        try:
            return await adapter.analyze_job(job_description)
        except MissingApiKeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except AIError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
            ) from exc

    async def generate_resume(
        self,
        user: User,
        payload: ResumeGenerateRequest,
    ) -> ResumeGenerateResponse:
        """Executa o pipeline completo de 4 estágios gerando uma nova versão de currículo.

        Args:
            user: Candidato autenticado.
            payload: Parâmetros da geração e vaga de destino.

        Returns:
            ResumeGenerateResponse: Dados e identificadores do currículo gerado.

        Raises:
            HTTPException: 409 se houver geração em andamento, 422 se houver alucinação severa.
        """
        # Trava de concorrência por usuário
        if user.id in _ACTIVE_GENERATIONS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "GENERATION_ALREADY_IN_PROGRESS: Uma síntese de currículo "
                    "já está em execução."
                ),
            )

        _ACTIVE_GENERATIONS.add(user.id)

        try:
            adapter = self._resolve_gemini_adapter(user)

            # 1. Recupera o Dossiê Factual (Grounding Context)
            profile_service = ProfileService(self._db)
            raw_dossier = await profile_service.get_full_dossier(user.id)

            user_companies = [e.company_name for e in raw_dossier["experiences"]]
            user_positions = [e.position_title for e in raw_dossier["experiences"]]
            user_skills = [s.name for s in raw_dossier["skills"]]
            # Incorpora tecnologias das experiências e projetos como skills factuais
            for exp in raw_dossier["experiences"]:
                user_skills.extend(exp.tech_stack or [])
            for proj in raw_dossier["projects"]:
                user_skills.extend(proj.technologies or [])

            ground_truth: dict[str, Any] = {
                "companies": list(set(user_companies)),
                "positions": list(set(user_positions)),
                "skills": list(set(user_skills)),
                "educations": [
                    {"institution": ed.institution_name, "degree": ed.degree}
                    for ed in raw_dossier["educations"]
                ],
                "certifications": [c.name for c in raw_dossier["certifications"]],
                "projects": [p.title for p in raw_dossier["projects"]],
            }

            # 2. Resolução do Prompt Skill (Template de Persona)
            prompt_skill_stmt = select(PromptSkill).where(
                PromptSkill.slug == payload.prompt_skill_slug
            )
            prompt_skill_res = await self._db.execute(prompt_skill_stmt)
            prompt_skill = prompt_skill_res.scalar_one_or_none()

            instructions = (
                prompt_skill.system_prompt
                if prompt_skill
                else "Enfatize métricas numéricas, realizações e verbos de ação com clareza."
            )

            # 3. Estágio 3: Síntese Estruturada via LLM
            generated = await adapter.generate_resume(
                job_description=payload.job_description,
                user_dossier=ground_truth,
                prompt_skill_instructions=instructions,
                language=payload.language,
            )

            # 4. Estágio 4: Auditoria Algorítmica Anti-Alucinação
            content_dict = generated.model_dump()
            audit = self._audit_engine.audit(content_dict, ground_truth)

            if not audit.is_valid:
                culprit = (
                    audit.hallucinations[0].description
                    if audit.hallucinations
                    else "Score de confiança insuficiente"
                )
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Geração rejeitada pelo motor anti-alucinação: {culprit}",
                )

            # Poda silenciosa de competências menores se score >= 80%
            sanitized_content = self._audit_engine.sanitize(content_dict, audit)

            # 5. Vinculação com Candidatura (ATS)
            application_id = payload.application_id
            if application_id is None and payload.create_application:
                comp_name = payload.company_name or "Empresa Oportunidade"
                j_title = payload.job_title or "Cargo Pretendido"
                new_app = Application(
                    user_id=user.id,
                    company_name=comp_name,
                    job_title=j_title,
                    job_url=payload.job_url,
                    job_description=payload.job_description,
                    status="applied",
                )
                self._db.add(new_app)
                await self._db.flush()
                application_id = new_app.id
            elif application_id is not None:
                # Valida pertencimento do tenant
                app_check = await self._db.execute(
                    select(Application).where(
                        Application.id == application_id,
                        Application.user_id == user.id,
                        Application.deleted_at.is_(None),
                    )
                )
                if not app_check.scalar_one_or_none():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Candidatura informada não existe ou pertence a outro usuário.",
                    )

            if not application_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ID de candidatura ausente e create_application está desativado.",
                )

            # Determina número da versão sequencial
            version_stmt = select(
                func.coalesce(func.max(GeneratedResume.version_number), 0)
            ).where(GeneratedResume.application_id == application_id)
            curr_version = (await self._db.execute(version_stmt)).scalar() or 0
            next_version = curr_version + 1

            # 6. Persistência do Snapshot Imutável da Versão
            resume = GeneratedResume(
                application_id=application_id,
                user_id=user.id,
                prompt_skill_id=prompt_skill.id if prompt_skill else None,
                language=payload.language,
                version_number=next_version,
                structured_content=sanitized_content,
                match_analysis=sanitized_content.get("match_analysis", {}),
                match_percentage=sanitized_content.get(
                    "match_percentage", audit.trust_score
                ),
            )
            self._db.add(resume)
            await self._db.flush()

            return ResumeGenerateResponse(
                resume_id=resume.id,
                application_id=application_id,
                version_number=resume.version_number,
                match_percentage=resume.match_percentage,
                match_analysis=resume.match_analysis,
                structured_content=resume.structured_content,
            )

        finally:
            _ACTIVE_GENERATIONS.discard(user.id)

    async def match_preview(
        self,
        user: User,
        job_description: str,
    ) -> MatchPreviewResponse:
        """Calcula a aderência do candidato contra a vaga antes da geração do currículo.

        Args:
            user: Usuário solicitante.
            job_description: Texto descritivo da vaga.

        Returns:
            MatchPreviewResponse com pontuação e matriz de correspondência.
        """
        adapter = self._resolve_gemini_adapter(user)
        job_analysis = await adapter.analyze_job(job_description)

        profile_service = ProfileService(self._db)
        raw_dossier = await profile_service.get_full_dossier(user.id)
        dossier: dict[str, Any] = {
            "skills": [s.name for s in raw_dossier["skills"]],
            "experiences": [
                {
                    "company_name": e.company_name,
                    "position_title": e.position_title,
                    "tech_stack": e.tech_stack or [],
                    "bullet_points": e.achievements or [],
                }
                for e in raw_dossier["experiences"]
            ],
            "certifications": [c.name for c in raw_dossier["certifications"]],
        }

        engine = VectorMatchEngine()
        result = engine.evaluate_match(dossier=dossier, job_analysis=job_analysis)

        return MatchPreviewResponse(
            match_percentage=result.match_percentage,
            mandatory_matches=[
                MatchAnalysisItemSchema(
                    requirement=m.requirement,
                    status=m.status,
                    evidence=m.evidence,
                    similarity_score=m.similarity_score,
                )
                for m in result.mandatory_matches
            ],
            desirable_matches=[
                MatchAnalysisItemSchema(
                    requirement=m.requirement,
                    status=m.status,
                    evidence=m.evidence,
                    similarity_score=m.similarity_score,
                )
                for m in result.desirable_matches
            ],
            missing_mandatory=result.missing_mandatory,
            missing_desirable=result.missing_desirable,
            suggested_keywords=result.suggested_keywords,
        )

