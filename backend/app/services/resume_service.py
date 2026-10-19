"""Serviço central de geração inteligente de currículos com IA (Google Gemini).

Orquestra o pipeline em 4 estágios:
1. Decomposição semântica da vaga (gemini-1.5-flash)
2. Injeção restritiva do Grounding Context (fatos do banco relacional)
3. Síntese via Structured Outputs (FullGeneratedResumePayload)
4. Auditoria algorítmica determinística anti-alucinação (GroundingAuditEngine)
"""

import os
import time
import uuid
from datetime import UTC, datetime
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
from app.core.logging import get_logger
from app.core.vector_match import VectorMatchEngine
from app.domain.models import (
    Application,
    ApplicationNote,
    GeneratedResume,
    PromptSkill,
    User,
)
from app.ports.ai_port import (
    AIError,
    ChatMessage,
    JobAnalysisResult,
    MissingApiKeyError,
)
from app.services.profile_service import ProfileService

logger = get_logger(__name__)

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

    def _build_ground_truth(self, raw_dossier: dict[str, Any]) -> dict[str, Any]:
        """Constrói o repositório factual estruturado do candidato para o grounding da LLM."""
        user_companies = [
            e.company_name
            for e in raw_dossier.get("experiences", [])
            if hasattr(e, "company_name") and isinstance(e.company_name, str)
        ]
        user_positions = [
            e.position_title
            for e in raw_dossier.get("experiences", [])
            if hasattr(e, "position_title") and isinstance(e.position_title, str)
        ]
        user_skills = [
            s.name
            for s in raw_dossier.get("skills", [])
            if hasattr(s, "name") and isinstance(s.name, str)
        ]
        for exp in raw_dossier.get("experiences", []):
            stack = getattr(exp, "tech_stack", [])
            if isinstance(stack, list):
                user_skills.extend(s for s in stack if isinstance(s, str))
        for proj in raw_dossier.get("projects", []):
            techs = getattr(proj, "technologies", [])
            if isinstance(techs, list):
                user_skills.extend(t for t in techs if isinstance(t, str))

        def _safe_str(obj: Any, attr: str, default: str = "") -> str:
            val = getattr(obj, attr, default)
            return val if isinstance(val, str) else default

        def _safe_list(obj: Any, attr: str) -> list[str]:
            val = getattr(obj, attr, [])
            return [x for x in val if isinstance(x, str)] if isinstance(val, list) else []

        return {
            "companies": list(set(user_companies)),
            "positions": list(set(user_positions)),
            "skills": list(set(user_skills)),
            "experiences": [
                {
                    "company": _safe_str(exp, "company_name"),
                    "position": _safe_str(exp, "position_title"),
                    "start_date": (
                        exp.start_date.isoformat()
                        if hasattr(getattr(exp, "start_date", None), "isoformat")
                        else _safe_str(exp, "start_date")
                    ),
                    "end_date": (
                        exp.end_date.isoformat()
                        if getattr(exp, "end_date", None) and hasattr(exp.end_date, "isoformat")
                        else (
                            _safe_str(exp, "end_date") if getattr(exp, "end_date", None) else None
                        )
                    ),
                    "is_current": bool(getattr(exp, "is_current", False)),
                    "description": _safe_str(exp, "description"),
                    "achievements": _safe_list(exp, "bullet_points"),
                    "bullet_points": _safe_list(exp, "bullet_points"),
                    "tech_stack": _safe_list(exp, "tech_stack"),
                    "quantifiable_results": _safe_list(exp, "quantifiable_results"),
                }
                for exp in raw_dossier.get("experiences", [])
            ],
            "educations": [
                {
                    "institution": _safe_str(ed, "institution_name"),
                    "degree": _safe_str(ed, "degree"),
                    "field_of_study": _safe_str(ed, "field_of_study"),
                }
                for ed in raw_dossier.get("educations", [])
            ],
            "certifications": [
                {
                    "name": _safe_str(c, "name") if hasattr(c, "name") else str(c),
                    "issuing_organization": _safe_str(c, "issuing_organization"),
                }
                if hasattr(c, "name")
                else str(c)
                for c in raw_dossier.get("certifications", [])
            ],
            "projects": [
                {
                    "title": _safe_str(p, "title") if hasattr(p, "title") else str(p),
                    "role": _safe_str(p, "role"),
                    "description": _safe_str(p, "description"),
                    "technologies": _safe_list(p, "technologies"),
                }
                for p in raw_dossier.get("projects", [])
            ],
            "languages": [
                {
                    "language": _safe_str(lang, "language_name") or str(lang),
                    "proficiency": _safe_str(lang, "proficiency_level", "professional"),
                }
                for lang in raw_dossier.get("languages", [])
            ],
        }

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
            # Dados Adicionais Autenticados (AAD) do usuário para garantir isolamento multi-tenant
            user_associated_data = str(user.id).encode("utf-8")
            try:
                api_key = crypto_service.decrypt(
                    user.settings.encrypted_gemini_api_key,
                    associated_data=user_associated_data,
                )
            except Exception as dec_exc:
                logger.warning(
                    "gemini_api_key_aad_decryption_fallback",
                    user_id=str(user.id),
                    error=str(dec_exc),
                )
                try:
                    # Fallback suave para chaves legadas decifradas sem associated_data
                    api_key = crypto_service.decrypt(user.settings.encrypted_gemini_api_key)
                except Exception as raw_dec_exc:
                    logger.error(
                        "gemini_api_key_decryption_failed",
                        user_id=str(user.id),
                        error=str(raw_dec_exc),
                        exc_info=True,
                    )
                    api_key = None

        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            logger.warning(
                "gemini_api_key_not_configured",
                user_id=str(user.id),
                has_user_settings=bool(user.settings),
                has_encrypted_key=bool(user.settings and user.settings.encrypted_gemini_api_key),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chave de API do Gemini não configurada. "
                "Cadastre sua chave pessoal (BYOK) nas configurações de conta.",
            )

        model = user.settings.gemini_model if user.settings and user.settings.gemini_model else None
        thinking_level = (
            user.settings.gemini_thinking_level
            if user.settings and user.settings.gemini_thinking_level
            else None
        )
        return GeminiAIAdapter(api_key=api_key, model=model, thinking_level=thinking_level)

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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except AIError as exc:
            logger.error(
                "resume_service_analyze_job_upstream_error",
                user_id=str(user.id),
                error=str(exc),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Falha na comunicação com o provedor de IA. Tente novamente mais tarde.",
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
            logger.warning(
                "resume_generation_concurrency_conflict",
                user_id=str(user.id),
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "GENERATION_ALREADY_IN_PROGRESS: Uma síntese de currículo já está em execução."
                ),
            )

        _ACTIVE_GENERATIONS.add(user.id)

        try:
            total_start_time = time.perf_counter()

            # Validação prévia de candidatura (fail-fast antes de invocar LLM)
            application_id = payload.application_id
            if application_id is None and not payload.create_application:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ID de candidatura ausente e create_application está desativado.",
                )
            if application_id is not None:
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

            adapter = self._resolve_gemini_adapter(user)

            # 1. Recupera o Dossiê Factual (Grounding Context)
            logger.info(
                "resume_generation_stage_started",
                stage=1,
                stage_name="ground_truth_retrieval",
                user_id=str(user.id),
            )
            profile_service = ProfileService(self._db)
            raw_dossier = await profile_service.get_full_dossier(user.id)

            ground_truth = self._build_ground_truth(raw_dossier)

            logger.info(
                "resume_generation_stage_completed",
                stage=1,
                stage_name="ground_truth_retrieval",
                user_id=str(user.id),
                companies_count=len(ground_truth["companies"]),
                positions_count=len(ground_truth["positions"]),
                skills_count=len(ground_truth["skills"]),
                educations_count=len(ground_truth["educations"]),
                certifications_count=len(ground_truth["certifications"]),
                projects_count=len(ground_truth["projects"]),
            )

            if not ground_truth["skills"] and not ground_truth["companies"]:
                logger.warning(
                    "resume_generation_empty_dossier_detected",
                    user_id=str(user.id),
                )

            # 2. Resolução do Prompt Skill (Template de Persona)
            logger.info(
                "resume_generation_stage_started",
                stage=2,
                stage_name="prompt_skill_resolution",
                prompt_skill_slug=payload.prompt_skill_slug,
            )
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
            stage3_start = time.perf_counter()
            logger.info(
                "resume_generation_stage_started",
                stage=3,
                stage_name="llm_synthesis",
                language=payload.language,
                user_id=str(user.id),
            )
            generated = await adapter.generate_resume(
                job_description=payload.job_description,
                user_dossier=ground_truth,
                prompt_skill_instructions=instructions,
                language=payload.language,
            )
            stage3_duration_ms = round((time.perf_counter() - stage3_start) * 1000, 2)
            raw_tokens = getattr(adapter, "last_token_usage", 0)
            total_tokens = raw_tokens if isinstance(raw_tokens, int) else 0
            if total_tokens > 0:
                from app.services.token_service import record_token_usage

                await record_token_usage(self._db, user, total_tokens)

            logger.info(
                "resume_generation_stage_completed",
                stage=3,
                stage_name="llm_synthesis",
                user_id=str(user.id),
                duration_ms=stage3_duration_ms,
                total_tokens=total_tokens,
            )

            # 4. Estágio 4: Auditoria Algorítmica Anti-Alucinação
            logger.info(
                "resume_generation_stage_started",
                stage=4,
                stage_name="grounding_audit",
            )
            content_dict = generated.model_dump()
            audit = self._audit_engine.audit(content_dict, ground_truth)

            if not audit.is_valid:
                total_duration_ms = round((time.perf_counter() - total_start_time) * 1000, 2)
                culprit = (
                    audit.hallucinations[0].description
                    if audit.hallucinations
                    else "Score de confiança insuficiente"
                )
                logger.warning(
                    "resume_generation_audit_rejected",
                    user_id=str(user.id),
                    trust_score=audit.trust_score,
                    hallucinations_count=len(audit.hallucinations),
                    culprit=culprit,
                    total_duration_ms=total_duration_ms,
                )
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Geração rejeitada pelo motor anti-alucinação: {culprit}",
                )

            # Poda silenciosa de competências menores se score >= 80%
            sanitized_content = self._audit_engine.sanitize(content_dict, audit)

            # 5. Vinculação com Candidatura (ATS)
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

            assert application_id is not None

            # Determina número da versão sequencial
            version_stmt = select(func.coalesce(func.max(GeneratedResume.version_number), 0)).where(
                GeneratedResume.application_id == application_id
            )
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
                match_percentage=sanitized_content.get("match_percentage", audit.trust_score),
            )
            self._db.add(resume)
            await self._db.flush()

            total_duration_ms = round((time.perf_counter() - total_start_time) * 1000, 2)
            logger.info(
                "resume_generation_completed",
                resume_id=str(resume.id),
                user_id=str(user.id),
                application_id=str(application_id),
                version_number=resume.version_number,
                match_percentage=resume.match_percentage,
                trust_score=audit.trust_score,
                total_duration_ms=total_duration_ms,
            )

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

    async def regenerate_resume_from_chat(
        self,
        user: User,
        resume_id: uuid.UUID,
        chat_messages: list[ChatMessage],
        prompt_skill_slug: str | None = None,
    ) -> ResumeGenerateResponse:
        """Sintetiza uma nova versão do currículo incorporando os direcionamentos do Copilot Chat.

        Args:
            user: Candidato autenticado.
            resume_id: Identificador do currículo baseline (versão atual).
            chat_messages: Histórico da conversa multi-turn com as orientações do usuário.
            prompt_skill_slug: Slug da metodologia/persona para calibrar o tom.

        Returns:
            ResumeGenerateResponse com identificador e snapshot da nova versão gerada.

        Raises:
            HTTPException: 409 se houver geração em andamento;
                           404 se o currículo ou vaga não existirem;
                           400 se o histórico for vazio;
                           422 se o motor anti-alucinação rejeitar a síntese.
        """
        if not chat_messages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O histórico de alinhamento com o Copilot não pode ser vazio para regerar.",
            )

        if user.id in _ACTIVE_GENERATIONS:
            logger.warning("resume_regeneration_concurrency_conflict", user_id=str(user.id))
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "GENERATION_ALREADY_IN_PROGRESS: Uma síntese de currículo já está em execução."
                ),
            )

        _ACTIVE_GENERATIONS.add(user.id)

        try:
            total_start_time = time.perf_counter()

            # 1. Recupera o currículo baseline e a candidatura
            stmt_resume = select(GeneratedResume).where(
                GeneratedResume.id == resume_id,
                GeneratedResume.user_id == user.id,
            )
            res_resume = await self._db.execute(stmt_resume)
            base_resume = res_resume.scalar_one_or_none()
            if not base_resume:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Currículo base não encontrado ou pertence a outro usuário.",
                )

            application_id = base_resume.application_id
            if not application_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Currículo base não possui vínculo com uma oportunidade.",
                )

            stmt_app = select(Application).where(
                Application.id == application_id,
                Application.user_id == user.id,
                Application.deleted_at.is_(None),
            )
            res_app = await self._db.execute(stmt_app)
            application = res_app.scalar_one_or_none()
            if not application:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Candidatura vinculada não localizada.",
                )

            adapter = self._resolve_gemini_adapter(user)

            # 2. Recupera o Dossiê Factual
            profile_service = ProfileService(self._db)
            raw_dossier = await profile_service.get_full_dossier(user.id)
            ground_truth = self._build_ground_truth(raw_dossier)

            # 3. Resolução da Metodologia / PromptSkill
            slug_to_resolve = prompt_skill_slug
            if not slug_to_resolve and base_resume.prompt_skill_id:
                stmt_ps_base = select(PromptSkill).where(
                    PromptSkill.id == base_resume.prompt_skill_id
                )
                res_ps_base = await self._db.execute(stmt_ps_base)
                ps_base = res_ps_base.scalar_one_or_none()
                if ps_base:
                    slug_to_resolve = ps_base.slug

            slug_to_resolve = slug_to_resolve or "google-xyz"
            stmt_ps = select(PromptSkill).where(PromptSkill.slug == slug_to_resolve)
            res_ps = await self._db.execute(stmt_ps)
            prompt_skill = res_ps.scalar_one_or_none()

            instructions = (
                prompt_skill.system_prompt
                if prompt_skill
                else "Enfatize métricas numéricas, realizações e verbos de ação com clareza."
            )

            # 4. Síntese via Gemini com injeção do chat_history e previous_resume
            stage3_start = time.perf_counter()
            generated = await adapter.generate_resume(
                job_description=application.job_description,
                user_dossier=ground_truth,
                prompt_skill_instructions=instructions,
                language=base_resume.language or "pt-BR",
                chat_history=chat_messages,
                previous_resume=base_resume.structured_content,
            )
            stage3_duration_ms = round((time.perf_counter() - stage3_start) * 1000, 2)
            raw_tokens = getattr(adapter, "last_token_usage", 0)
            total_tokens = raw_tokens if isinstance(raw_tokens, int) else 0
            if total_tokens > 0:
                from app.services.token_service import record_token_usage

                await record_token_usage(self._db, user, total_tokens)

            logger.info(
                "resume_regeneration_stage_completed",
                stage=3,
                stage_name="llm_synthesis",
                user_id=str(user.id),
                duration_ms=stage3_duration_ms,
                total_tokens=total_tokens,
            )

            # 5. Auditoria Anti-Alucinação
            content_dict = generated.model_dump()
            audit = self._audit_engine.audit(content_dict, ground_truth)
            if not audit.is_valid:
                culprit = (
                    audit.hallucinations[0].description
                    if audit.hallucinations
                    else "Score de confiança insuficiente"
                )
                logger.warning(
                    "resume_regeneration_audit_rejected",
                    user_id=str(user.id),
                    culprit=culprit,
                )
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Regeração rejeitada pelo motor anti-alucinação: {culprit}",
                )

            sanitized_content = self._audit_engine.sanitize(content_dict, audit)

            # 6. Determinação sequencial do número de versão
            version_stmt = select(func.coalesce(func.max(GeneratedResume.version_number), 0)).where(
                GeneratedResume.application_id == application_id
            )
            curr_version = (await self._db.execute(version_stmt)).scalar() or 0
            next_version = curr_version + 1

            new_resume = GeneratedResume(
                application_id=application_id,
                user_id=user.id,
                prompt_skill_id=prompt_skill.id if prompt_skill else None,
                language=base_resume.language,
                version_number=next_version,
                structured_content=sanitized_content,
                match_analysis=sanitized_content.get("match_analysis", {}),
                match_percentage=sanitized_content.get("match_percentage", audit.trust_score),
            )
            self._db.add(new_resume)
            await self._db.flush()

            # Registra nota na candidatura
            regeneration_note = ApplicationNote(
                application_id=application_id,
                content=f"🚀 Nova versão calibrada gerada via Copilot IA (v{next_version}).",
                note_type="status_change",
            )
            self._db.add(regeneration_note)
            await self._db.flush()

            total_duration_ms = round((time.perf_counter() - total_start_time) * 1000, 2)
            logger.info(
                "resume_regeneration_completed",
                new_resume_id=str(new_resume.id),
                baseline_resume_id=str(base_resume.id),
                user_id=str(user.id),
                application_id=str(application_id),
                version_number=new_resume.version_number,
                total_duration_ms=total_duration_ms,
            )

            return ResumeGenerateResponse(
                resume_id=new_resume.id,
                application_id=application_id,
                version_number=new_resume.version_number,
                match_percentage=new_resume.match_percentage,
                match_analysis=new_resume.match_analysis,
                structured_content=new_resume.structured_content,
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
        start_time = time.perf_counter()
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
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        logger.info(
            "resume_match_preview_completed",
            user_id=str(user.id),
            match_percentage=result.match_percentage,
            mandatory_count=len(result.mandatory_matches),
            desirable_count=len(result.desirable_matches),
            duration_ms=duration_ms,
        )

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

    async def translate_resume(
        self,
        user: User,
        resume_id: uuid.UUID,
        target_language: str,
        current_content: dict[str, Any] | None = None,
    ) -> GeneratedResume:
        """Traduz o conteúdo de um currículo para o idioma alvo usando o adaptador de IA.

        Args:
            user: Usuário autenticado proprietário.
            resume_id: UUID do currículo a ser traduzido.
            target_language: Idioma de destino ('en-US', 'pt-BR', 'es-ES', etc.).
            current_content: Conteúdo mais recente do editor (opcional, fallback para banco).

        Returns:
            GeneratedResume: Registro atualizado com o conteúdo traduzido e novo idioma.

        Raises:
            HTTPException: Se o currículo não for encontrado.
            ModelUnavailableError: Se o modelo estiver temporariamente indisponível.
            AIError: Em caso de falha de IA.
        """
        stmt = select(GeneratedResume).where(
            GeneratedResume.id == resume_id,
            GeneratedResume.user_id == user.id,
        )
        res = await self._db.execute(stmt)
        resume = res.scalar_one_or_none()
        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Currículo não encontrado.",
            )

        content_to_translate = current_content or resume.structured_content
        adapter = self._resolve_gemini_adapter(user)

        start_time = time.perf_counter()
        translated_content = await adapter.translate_resume_content(
            content=content_to_translate,
            target_language=target_language,
        )
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        resume.structured_content = translated_content
        resume.language = target_language
        resume.updated_at = datetime.now(UTC)
        await self._db.commit()

        raw_tokens = getattr(adapter, "last_token_usage", 0)
        total_tokens = raw_tokens if isinstance(raw_tokens, int) else 0
        if total_tokens > 0:
            from app.services.token_service import record_token_usage

            await record_token_usage(self._db, user, total_tokens)

        logger.info(
            "resume_service_translation_completed",
            resume_id=str(resume_id),
            user_id=str(user.id),
            target_language=target_language,
            duration_ms=duration_ms,
            total_tokens=total_tokens,
        )
        return resume
