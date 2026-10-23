"""Serviço de orquestração do Agente Autônomo 'Job Hunter'.

Executa busca, raspagem segura, extração semântica de requisitos, avaliação de aderência
contra o Dossiê Mestre do usuário e pré-cadastro automatizado de candidaturas no ATS.
Obedece estritamente à Arquitetura Hexagonal recebendo AIPort e JobSourcePort via DI.
"""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.job_hunter import (
    JobHunterGoalConfig,
    JobHunterItemResult,
    JobHunterRunResponse,
)
from app.core.logging import get_logger
from app.core.url_scraper import PayloadTooLargeError, SSRFProtectionError
from app.core.vector_match import VectorMatchEngine
from app.domain.models import Application, ApplicationNote, Notification, User
from app.ports.ai_port import AIError, AIPort, MissingApiKeyError
from app.ports.job_hunter_port import (
    JobHunterSourceError,
    JobSourceBlockedError,
    JobSourceNetworkError,
    JobSourcePort,
    JobSourceRateLimitError,
    ScrapedJobPosting,
)
from app.services.profile_service import ProfileService

logger = get_logger(__name__)


class JobHunterService:
    """Orquestrador de ponta a ponta do agente autônomo Job Hunter.

    Attributes:
        db: Sessão ativa do banco de dados relacional.
        ai_port: Porta abstrata de integração com LLMs (Gemini).
        job_source_port: Porta abstrata de coleta e ingestão de vagas externas.
        match_engine: Motor determinístico de cálculo de aderência vetorial/semântica.
    """

    def __init__(
        self,
        db: AsyncSession,
        ai_port: AIPort,
        job_source_port: JobSourcePort,
    ) -> None:
        """Inicializa o serviço recebendo as portas via Inversão de Dependências."""
        self.db = db
        self.ai_port = ai_port
        self.job_source_port = job_source_port
        self.match_engine = VectorMatchEngine()

    def _build_match_dossier(self, raw_dossier: dict[str, Any]) -> dict[str, Any]:
        """Normaliza entidades do dossiê para a estrutura esperada pelo VectorMatchEngine.

        Args:
            raw_dossier: Dossiê retornado por ProfileService.get_full_dossier.

        Returns:
            dict[str, Any]: Dossiê normalizado com skills, experiences e certifications.
        """
        skills: list[str] = []
        for s in raw_dossier.get("skills", []):
            if hasattr(s, "name"):
                skills.append(str(s.name))
            elif isinstance(s, dict) and "name" in s:
                skills.append(str(s["name"]))
            else:
                skills.append(str(s))

        experiences: list[dict[str, Any]] = []
        for exp in raw_dossier.get("experiences", []):
            comp = (
                getattr(exp, "company_name", "")
                if hasattr(exp, "company_name")
                else (exp.get("company_name", "") if isinstance(exp, dict) else "")
            )
            title = (
                getattr(exp, "position_title", "")
                if hasattr(exp, "position_title")
                else (exp.get("position_title", "") if isinstance(exp, dict) else "")
            )
            stack = (
                getattr(exp, "tech_stack", [])
                if hasattr(exp, "tech_stack")
                else (exp.get("tech_stack", []) if isinstance(exp, dict) else [])
            )
            bullets = (
                getattr(exp, "bullet_points", [])
                if hasattr(exp, "bullet_points")
                else (exp.get("bullet_points", []) if isinstance(exp, dict) else [])
            )
            experiences.append(
                {
                    "company_name": comp or "",
                    "position_title": title or "",
                    "tech_stack": list(stack) if stack else [],
                    "bullet_points": list(bullets) if bullets else [],
                }
            )

        certifications: list[str] = []
        for c in raw_dossier.get("certifications", []):
            if hasattr(c, "name"):
                certifications.append(str(c.name))
            elif isinstance(c, dict) and "name" in c:
                certifications.append(str(c["name"]))
            else:
                certifications.append(str(c))

        return {
            "skills": skills,
            "experiences": experiences,
            "certifications": certifications,
        }

    async def _is_duplicate_application(
        self,
        user_id: uuid.UUID,
        source_url: str,
        company_name: str,
        job_title: str,
    ) -> bool:
        """Verifica se a oportunidade já foi cadastrada no funil ATS do usuário.

        Args:
            user_id: UUID do usuário autenticado.
            source_url: URL pública da oportunidade.
            company_name: Nome da empresa anunciante.
            job_title: Título da vaga.

        Returns:
            bool: True se já existir candidatura ativa correspondente.
        """
        conditions = [
            and_(
                func.lower(Application.company_name) == company_name.strip().lower(),
                func.lower(Application.job_title) == job_title.strip().lower(),
            )
        ]
        if source_url and source_url.strip():
            conditions.append(Application.job_url == source_url.strip())

        query = (
            select(Application.id)
            .where(
                Application.user_id == user_id,
                Application.deleted_at.is_(None),
                or_(*conditions),
            )
            .limit(1)
        )
        res = await self.db.execute(query)
        return res.scalar_one_or_none() is not None

    def _matches_career_goals(
        self,
        posting: ScrapedJobPosting,
        analyzed_title: str,
        goals: JobHunterGoalConfig,
    ) -> tuple[bool, str]:
        """Avalia se a vaga respeita os filtros e restrições de carreira do candidato.

        Args:
            posting: Vaga extraída pela porta de scraping.
            analyzed_title: Título da vaga refinado pela IA.
            goals: Metas e parâmetros de busca do usuário.

        Returns:
            tuple[bool, str]: (Aprovado, Justificativa da decisão).
        """
        # 1. Empresas descartadas (Blocklist)
        if goals.excluded_companies:
            posting_company_lower = (posting.company_name or "").strip().lower()
            for ex_comp in goals.excluded_companies:
                ex_clean = ex_comp.strip().lower()
                if ex_clean and (
                    ex_clean == posting_company_lower or ex_clean in posting_company_lower
                ):
                    return (
                        False,
                        f"Empresa '{posting.company_name}' está na lista de exclusão do usuário.",
                    )

        # 2. Modelo de trabalho permitido
        if goals.allowed_work_models and posting.work_model not in goals.allowed_work_models:
            return (
                False,
                f"Modelo de trabalho '{posting.work_model}' incompatível com as metas "
                f"({', '.join(goals.allowed_work_models)}).",
            )

        # 3. Escopo de cargos-alvo (Target Roles)
        if goals.target_roles:
            analyzed_lower = analyzed_title.lower()
            job_title_lower = (posting.job_title or "").lower()
            raw_desc_lower = (posting.raw_description or "").lower()
            matches_role = any(
                role.strip().lower() in analyzed_lower
                or role.strip().lower() in job_title_lower
                or role.strip().lower() in raw_desc_lower
                for role in goals.target_roles
                if role.strip()
            )
            if not matches_role:
                return (
                    False,
                    "Cargo/perfil da vaga fora do escopo de cargos-alvo definidos pelo usuário.",
                )

        # 4. Compatível
        return True, "Critérios de carreira compatíveis."

    async def hunt_and_triage(
        self,
        user: User,
        goals: JobHunterGoalConfig,
    ) -> JobHunterRunResponse:
        """Executa a triagem autônoma de um lote de URLs de vagas de emprego.

        Args:
            user: Usuário autenticado proprietário do pipeline.
            goals: Configuração de metas, scores mínimos e URLs de entrada.

        Returns:
            JobHunterRunResponse: Relatório consolidado da execução e pré-candidaturas.

        Raises:
            HTTPException: 400 se a chave do Gemini estiver ausente.
        """
        start_time = time.perf_counter()
        logger.info(
            "job_hunter_triage_started",
            user_id=str(user.id),
            sources_count=len(goals.source_urls),
            min_match_score=goals.min_match_score,
            auto_pre_apply=goals.auto_pre_apply,
        )

        profile_service = ProfileService(self.db)
        raw_dossier = await profile_service.get_full_dossier(user.id)
        dossier = self._build_match_dossier(raw_dossier)

        processed_count = 0
        pre_applied_count = 0
        rejected_count = 0
        skipped_duplicate_count = 0
        failed_count = 0
        results: list[JobHunterItemResult] = []

        for url in goals.source_urls:
            # Etapa A: Ingestão resiliente da fonte da vaga
            try:
                posting = await self.job_source_port.fetch_job_posting(url)
            except SSRFProtectionError as exc:
                logger.warning("job_hunter_source_ssrf_blocked", url=url, error=str(exc))
                results.append(
                    JobHunterItemResult(
                        source_url=url,
                        decision="failed_source",
                        reason="URL bloqueada pela proteção anti-SSRF.",
                        error_code="SSRF_BLOCKED",
                    )
                )
                failed_count += 1
                continue
            except PayloadTooLargeError as exc:
                logger.warning("job_hunter_source_payload_too_large", url=url, error=str(exc))
                results.append(
                    JobHunterItemResult(
                        source_url=url,
                        decision="failed_source",
                        reason="Payload da página excede o limite de segurança.",
                        error_code="PAYLOAD_TOO_LARGE",
                    )
                )
                failed_count += 1
                continue
            except JobSourceRateLimitError as exc:
                logger.warning("job_hunter_source_rate_limited", url=url, error=str(exc))
                results.append(
                    JobHunterItemResult(
                        source_url=url,
                        decision="failed_source",
                        reason="Fonte temporariamente indisponível por rate limiting (HTTP 429).",
                        error_code="RATE_LIMITED",
                    )
                )
                failed_count += 1
                continue
            except JobSourceBlockedError as exc:
                logger.warning("job_hunter_source_blocked", url=url, error=str(exc))
                results.append(
                    JobHunterItemResult(
                        source_url=url,
                        decision="failed_source",
                        reason="Acesso bloqueado pelo portal/ATS de origem (HTTP 403).",
                        error_code="SOURCE_BLOCKED",
                    )
                )
                failed_count += 1
                continue
            except (JobHunterSourceError, JobSourceNetworkError) as exc:
                logger.warning("job_hunter_source_network_error", url=url, error=str(exc))
                results.append(
                    JobHunterItemResult(
                        source_url=url,
                        decision="failed_source",
                        reason="Falha de rede ou timeout ao consultar a fonte da vaga.",
                        error_code="NETWORK_ERROR",
                    )
                )
                failed_count += 1
                continue

            # Etapa B: Verificação de duplicidade no funil ATS
            is_dup = await self._is_duplicate_application(
                user_id=user.id,
                source_url=url,
                company_name=posting.company_name,
                job_title=posting.job_title,
            )
            if is_dup:
                results.append(
                    JobHunterItemResult(
                        source_url=url,
                        company_name=posting.company_name,
                        job_title=posting.job_title,
                        work_model=posting.work_model,
                        decision="skipped_duplicate",
                        reason="Oportunidade já cadastrada no funil ATS do usuário.",
                    )
                )
                skipped_duplicate_count += 1
                processed_count += 1
                continue

            # Etapa C: Extração semântica de requisitos via IA
            try:
                job_analysis = await self.ai_port.analyze_job(posting.raw_description)
            except MissingApiKeyError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Chave de API do Gemini não configurada. Cadastre sua chave pessoal (BYOK) "
                        "nas configurações de conta."
                    ),
                ) from exc
            except AIError as exc:
                logger.warning(
                    "job_hunter_ai_analysis_failed",
                    url=url,
                    error=str(exc),
                    exc_info=True,
                )
                results.append(
                    JobHunterItemResult(
                        source_url=url,
                        company_name=posting.company_name,
                        job_title=posting.job_title,
                        work_model=posting.work_model,
                        decision="failed_source",
                        reason="Falha temporária na extração de requisitos via IA.",
                        error_code="AI_EXTRACTION_ERROR",
                    )
                )
                failed_count += 1
                continue

            # Etapa D: Refinamento de título e avaliação semântica de aderência
            effective_title = (
                job_analysis.job_title.strip() if job_analysis.job_title else posting.job_title
            )
            if not effective_title:
                effective_title = posting.job_title

            eval_res = self.match_engine.evaluate_match(dossier, job_analysis)

            # Etapa E: Verificação de conformidade com as metas de carreira
            goals_ok, goals_reason = self._matches_career_goals(posting, effective_title, goals)
            if not goals_ok:
                results.append(
                    JobHunterItemResult(
                        source_url=url,
                        company_name=posting.company_name,
                        job_title=effective_title,
                        work_model=posting.work_model,
                        decision="rejected_criteria_mismatch",
                        reason=goals_reason,
                        match_percentage=eval_res.match_percentage,
                        mandatory_requirements=job_analysis.mandatory_requirements,
                        missing_requirements=eval_res.missing_mandatory,
                    )
                )
                rejected_count += 1
                processed_count += 1
                continue

            if eval_res.match_percentage < goals.min_match_score:
                results.append(
                    JobHunterItemResult(
                        source_url=url,
                        company_name=posting.company_name,
                        job_title=effective_title,
                        work_model=posting.work_model,
                        decision="rejected_low_match",
                        reason=(
                            f"Score de aderência ({eval_res.match_percentage}%) abaixo do mínimo "
                            f"configurado ({goals.min_match_score}%)."
                        ),
                        match_percentage=eval_res.match_percentage,
                        mandatory_requirements=job_analysis.mandatory_requirements,
                        missing_requirements=eval_res.missing_mandatory,
                    )
                )
                rejected_count += 1
                processed_count += 1
                continue

            # Etapa F: Aprovação da oportunidade
            if goals.auto_pre_apply:
                app = Application(
                    user_id=user.id,
                    company_name=posting.company_name,
                    job_title=effective_title[:120],
                    job_url=url[:500],
                    job_description=posting.raw_description,
                    salary_range=posting.salary_range,
                    location=posting.location,
                    work_model=posting.work_model,
                    status="saved",
                    reminder_active=True,
                    last_activity_at=datetime.now(UTC),
                )
                self.db.add(app)
                await self.db.flush()

                satisfied_mand = len(job_analysis.mandatory_requirements) - len(
                    eval_res.missing_mandatory
                )
                total_mand = len(job_analysis.mandatory_requirements)

                note = ApplicationNote(
                    application_id=app.id,
                    note_type="general",
                    content=(
                        f"[Job Hunter AI] Triagem autônoma aprovada com "
                        f"{eval_res.match_percentage}% de match. "
                        f"Requisitos atendidos: {satisfied_mand}/{total_mand}."
                    ),
                )
                self.db.add(note)

                notification = Notification(
                    user_id=user.id,
                    application_id=app.id,
                    notification_type="job_hunter_match",
                    title=(
                        f"Nova Vaga Triada ({eval_res.match_percentage}%): {posting.company_name}"
                    ),
                    message=(
                        f"O agente Job Hunter pré-cadastrou a oportunidade '{effective_title}' "
                        f"({posting.company_name}) com {eval_res.match_percentage}% de aderência "
                        "ao seu perfil."
                    ),
                    is_read=False,
                    scheduled_for=datetime.now(UTC),
                    sent_at=datetime.now(UTC),
                )
                self.db.add(notification)

                await self.db.commit()

                pre_applied_count += 1
                processed_count += 1
                results.append(
                    JobHunterItemResult(
                        source_url=url,
                        company_name=posting.company_name,
                        job_title=effective_title,
                        work_model=posting.work_model,
                        decision="pre_applied",
                        reason=(
                            f"Vaga pré-cadastrada no ATS com {eval_res.match_percentage}% de match."
                        ),
                        match_percentage=eval_res.match_percentage,
                        mandatory_requirements=job_analysis.mandatory_requirements,
                        missing_requirements=eval_res.missing_mandatory,
                        application_id=app.id,
                    )
                )
            else:
                processed_count += 1
                results.append(
                    JobHunterItemResult(
                        source_url=url,
                        company_name=posting.company_name,
                        job_title=effective_title,
                        work_model=posting.work_model,
                        decision="approved_manual",
                        reason=(
                            f"Vaga aprovada na triagem ({eval_res.match_percentage}% de match) "
                            f"aguardando revisão manual."
                        ),
                        match_percentage=eval_res.match_percentage,
                        mandatory_requirements=job_analysis.mandatory_requirements,
                        missing_requirements=eval_res.missing_mandatory,
                    )
                )

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "job_hunter_triage_completed",
            user_id=str(user.id),
            duration_ms=duration_ms,
            total_sources=len(goals.source_urls),
            processed_count=processed_count,
            pre_applied_count=pre_applied_count,
            rejected_count=rejected_count,
            skipped_duplicate_count=skipped_duplicate_count,
            failed_count=failed_count,
        )

        return JobHunterRunResponse(
            total_sources=len(goals.source_urls),
            processed_count=processed_count,
            pre_applied_count=pre_applied_count,
            rejected_count=rejected_count,
            failed_count=failed_count,
            skipped_duplicate_count=skipped_duplicate_count,
            results=results,
        )
