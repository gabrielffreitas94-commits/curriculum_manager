"""Serviço de gerenciamento do ATS Core e ciclo de vida de candidaturas.

Implementa regras de negócio para cálculo proativo de follow-up (7 dias),
transição de etapas de processos seletivos, adição de contatos e notas e
agregação analítica das métricas de conversão do usuário candidato.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
from app.domain.models import (
    Application,
    ApplicationContact,
    ApplicationNote,
    ApplicationStage,
    GeneratedResume,
    User,
)

FOLLOW_UP_THRESHOLD_DAYS = 7


class ApplicationService:
    """Orquestrador das regras de negócio do ATS pessoal e gestão de candidaturas."""

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o serviço com a sessão transacional do banco de dados.

        Args:
            db: Sessão ativa do SQLAlchemy AsyncSession.
        """
        self.db = db

    def _compute_needs_follow_up(self, app: Application) -> bool:
        """Determina se uma candidatura está estagnada há mais de 7 dias sem resposta.

        Regras de Negócio:
            1. Status finais ('rejected', 'offer', 'withdrawn') nunca exigem follow-up.
            2. Se o usuário desativou reminder_active, retorna False.
            3. Compara o intervalo entre UTC now e last_activity_at contra o limiar de 7 dias.

        Args:
            app: Instância do modelo relacional Application.

        Returns:
            True se necessita de contato proativo, False caso contrário.
        """
        if not app.reminder_active:
            return False

        if app.status in ("rejected", "offer", "withdrawn"):
            return False

        last_act = app.last_activity_at
        if last_act.tzinfo is None:
            last_act = last_act.replace(tzinfo=UTC)

        delta = datetime.now(UTC) - last_act
        return delta.total_seconds() > (FOLLOW_UP_THRESHOLD_DAYS * 86400)

    async def list_applications(
        self,
        user: User,
        status_filter: str | None = None,
        needs_follow_up: bool | None = None,
    ) -> list[ApplicationListItemResponse]:
        """Lista as candidaturas ativas do usuário candidato com flags analíticas.

        Args:
            user: Usuário autenticado proprietário.
            status_filter: Filtro opcional por status do funil.
            needs_follow_up: Se fornecido, filtra apenas candidaturas pendentes de contato.

        Returns:
            Lista de candidaturas formatadas para visualização em tabela ou Kanban.
        """
        stmt = (
            select(Application)
            .where(
                Application.user_id == user.id,
                Application.deleted_at.is_(None),
            )
            .order_by(Application.last_activity_at.desc())
        )

        if status_filter:
            stmt = stmt.where(Application.status == status_filter)

        result = await self.db.execute(stmt)
        apps = result.scalars().all()

        items: list[ApplicationListItemResponse] = []
        for app in apps:
            is_stale = self._compute_needs_follow_up(app)
            if needs_follow_up is not None and is_stale != needs_follow_up:
                continue

            items.append(
                ApplicationListItemResponse(
                    id=app.id,
                    company_name=app.company_name,
                    job_title=app.job_title,
                    status=app.status,
                    work_model=app.work_model,
                    applied_at=app.applied_at,
                    last_activity_at=app.last_activity_at,
                    needs_follow_up=is_stale,
                    location=app.location,
                    salary_range=app.salary_range,
                )
            )

        return items

    async def create_application(
        self,
        user: User,
        payload: ApplicationCreate,
    ) -> ApplicationListItemResponse:
        """Registra uma nova candidatura no funil ATS.

        Args:
            user: Usuário autenticado solicitante.
            payload: Dados estruturados da vaga.

        Returns:
            Candidatura recém-criada serializada.
        """
        app = Application(
            user_id=user.id,
            company_name=payload.company_name,
            job_title=payload.job_title,
            job_description=payload.job_description,
            job_url=payload.job_url,
            work_model=payload.work_model,
            salary_range=payload.salary_range,
            location=payload.location,
            status=payload.status,
            next_follow_up_date=payload.next_follow_up_date,
            reminder_active=payload.reminder_active,
            last_activity_at=datetime.now(UTC),
        )
        self.db.add(app)
        await self.db.commit()
        await self.db.refresh(app)

        return ApplicationListItemResponse(
            id=app.id,
            company_name=app.company_name,
            job_title=app.job_title,
            status=app.status,
            work_model=app.work_model,
            applied_at=app.applied_at,
            last_activity_at=app.last_activity_at,
            needs_follow_up=False,
            location=app.location,
            salary_range=app.salary_range,
        )

    async def get_application_detail(
        self,
        user: User,
        app_id: uuid.UUID,
    ) -> ApplicationDetailResponse:
        """Obtém o dossiê completo de uma vaga incluindo etapas, contatos e notas.

        Args:
            user: Usuário autenticado proprietário.
            app_id: UUID da candidatura.

        Returns:
            ApplicationDetailResponse com nós filhos carregados.

        Raises:
            HTTPException: 404 caso não exista ou não pertença ao usuário.
        """
        stmt = (
            select(Application)
            .options(
                selectinload(Application.stages),
                selectinload(Application.contacts),
                selectinload(Application.notes),
            )
            .where(
                Application.id == app_id,
                Application.user_id == user.id,
                Application.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        app = result.scalar_one_or_none()

        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidatura não encontrada ou não pertence ao usuário.",
            )

        stages_resp = [
            ApplicationStageResponse.model_validate(st)
            for st in sorted(app.stages, key=lambda s: s.order_index)
        ]

        contacts_resp = [
            ApplicationContactResponse(
                id=c.id,
                application_id=c.application_id,
                name=c.full_name,
                full_name=c.full_name,
                role=c.role_type,
                role_type=c.role_type,
                email=c.email,
                phone=c.phone,
                linkedin_url=c.linkedin_url,
                context_notes=c.context_notes,
                created_at=c.created_at,
            )
            for c in app.contacts
        ]

        notes_resp = [
            ApplicationNoteResponse.model_validate(n)
            for n in sorted(app.notes, key=lambda n: n.created_at, reverse=True)
        ]

        return ApplicationDetailResponse(
            id=app.id,
            company_name=app.company_name,
            job_title=app.job_title,
            job_description=app.job_description,
            job_url=app.job_url,
            status=app.status,
            work_model=app.work_model,
            salary_range=app.salary_range,
            location=app.location,
            applied_at=app.applied_at,
            last_activity_at=app.last_activity_at,
            next_follow_up_date=app.next_follow_up_date,
            reminder_active=app.reminder_active,
            needs_follow_up=self._compute_needs_follow_up(app),
            stages=stages_resp,
            contacts=contacts_resp,
            notes=notes_resp,
        )

    async def update_application(
        self,
        user: User,
        app_id: uuid.UUID,
        payload: ApplicationUpdate,
    ) -> ApplicationListItemResponse:
        """Atualiza metadados ou avança o status de uma candidatura.

        Args:
            user: Usuário autenticado proprietário.
            app_id: UUID da oportunidade.
            payload: Campos parciais a atualizar.

        Returns:
            ApplicationListItemResponse atualizado.

        Raises:
            HTTPException: 404 se não encontrada.
        """
        stmt = select(Application).where(
            Application.id == app_id,
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        app = result.scalar_one_or_none()

        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidatura não encontrada para atualização.",
            )

        update_data = payload.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            setattr(app, key, val)

        app.last_activity_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(app)

        return ApplicationListItemResponse(
            id=app.id,
            company_name=app.company_name,
            job_title=app.job_title,
            status=app.status,
            work_model=app.work_model,
            applied_at=app.applied_at,
            last_activity_at=app.last_activity_at,
            needs_follow_up=self._compute_needs_follow_up(app),
            location=app.location,
            salary_range=app.salary_range,
        )

    async def delete_application(self, user: User, app_id: uuid.UUID) -> None:
        """Executa soft-delete em uma candidatura.

        Args:
            user: Usuário proprietário.
            app_id: UUID da oportunidade.

        Raises:
            HTTPException: 404 se não encontrada.
        """
        stmt = select(Application).where(
            Application.id == app_id,
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        app = result.scalar_one_or_none()

        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidatura não encontrada para remoção.",
            )

        app.deleted_at = datetime.now(UTC)
        await self.db.commit()

    async def add_stage(
        self,
        user: User,
        app_id: uuid.UUID,
        payload: ApplicationStageCreate,
    ) -> ApplicationStageResponse:
        """Adiciona uma nova etapa no processo seletivo da vaga.

        Args:
            user: Usuário proprietário.
            app_id: UUID da candidatura.
            payload: Metadados da etapa.

        Returns:
            ApplicationStageResponse correspondente.
        """
        stmt = select(Application).where(
            Application.id == app_id,
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        app = result.scalar_one_or_none()

        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidatura não encontrada.",
            )

        stage = ApplicationStage(
            application_id=app.id,
            stage_name=payload.stage_name,
            status=payload.status,
            order_index=payload.order_index,
            scheduled_at=payload.scheduled_at,
            completed_at=payload.completed_at,
            feedback_notes=payload.feedback_notes,
        )
        self.db.add(stage)
        app.last_activity_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(stage)

        return ApplicationStageResponse.model_validate(stage)

    async def update_stage(
        self,
        user: User,
        app_id: uuid.UUID,
        stage_id: uuid.UUID,
        payload: ApplicationStageUpdate,
    ) -> ApplicationStageResponse:
        """Atualiza os detalhes ou status de uma etapa seletiva.

        Args:
            user: Usuário proprietário.
            app_id: UUID da candidatura pai.
            stage_id: UUID da etapa seletiva.
            payload: Alterações parciais.

        Returns:
            ApplicationStageResponse atualizado.
        """
        stmt = (
            select(ApplicationStage)
            .join(Application, Application.id == ApplicationStage.application_id)
            .where(
                ApplicationStage.id == stage_id,
                ApplicationStage.application_id == app_id,
                Application.user_id == user.id,
                Application.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        stage = result.scalar_one_or_none()

        if not stage:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Etapa seletiva não encontrada para a candidatura indicada.",
            )

        update_data = payload.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            setattr(stage, key, val)

        # Atualiza a atividade da candidatura pai
        stmt_app = select(Application).where(Application.id == app_id)
        res_app = await self.db.execute(stmt_app)
        app = res_app.scalar_one_or_none()
        if app:
            app.last_activity_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(stage)

        return ApplicationStageResponse.model_validate(stage)

    async def add_contact(
        self,
        user: User,
        app_id: uuid.UUID,
        payload: ApplicationContactCreate,
    ) -> ApplicationContactResponse:
        """Registra um recrutador ou entrevistador associado à vaga.

        Args:
            user: Usuário proprietário.
            app_id: UUID da candidatura.
            payload: Dados do contato.

        Returns:
            ApplicationContactResponse correspondente.
        """
        stmt = select(Application).where(
            Application.id == app_id,
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        app = result.scalar_one_or_none()

        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidatura não encontrada.",
            )

        full_name = payload.full_name or payload.name or "Contato de Recrutamento"
        role_type = payload.role_type or payload.role or "recruiter"

        contact = ApplicationContact(
            application_id=app.id,
            full_name=full_name,
            role_type=role_type,
            email=payload.email,
            phone=payload.phone,
            linkedin_url=payload.linkedin_url,
            context_notes=payload.context_notes,
        )
        self.db.add(contact)
        app.last_activity_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(contact)

        return ApplicationContactResponse(
            id=contact.id,
            application_id=contact.application_id,
            name=contact.full_name,
            full_name=contact.full_name,
            role=contact.role_type,
            role_type=contact.role_type,
            email=contact.email,
            phone=contact.phone,
            linkedin_url=contact.linkedin_url,
            context_notes=contact.context_notes,
            created_at=contact.created_at,
        )

    async def add_note(
        self,
        user: User,
        app_id: uuid.UUID,
        payload: ApplicationNoteCreate,
    ) -> ApplicationNoteResponse:
        """Adiciona uma anotação cronológica livre à vaga.

        Args:
            user: Usuário proprietário.
            app_id: UUID da candidatura.
            payload: Conteúdo e tipo da nota.

        Returns:
            ApplicationNoteResponse correspondente.
        """
        stmt = select(Application).where(
            Application.id == app_id,
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        app = result.scalar_one_or_none()

        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidatura não encontrada.",
            )

        note = ApplicationNote(
            application_id=app.id,
            content=payload.content,
            note_type=payload.note_type,
        )
        self.db.add(note)
        app.last_activity_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(note)

        return ApplicationNoteResponse.model_validate(note)

    async def get_analytics_metrics(self, user: User) -> ApplicationAnalyticsMetrics:
        """Calcula métricas agregadas de desempenho no funil e taxas de conversão.

        Args:
            user: Usuário autenticado solicitante.

        Returns:
            ApplicationAnalyticsMetrics com estatísticas consolidadas.
        """
        stmt = select(Application).where(
            Application.user_id == user.id,
            Application.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        apps = result.scalars().all()

        total = len(apps)
        status_dist: dict[str, int] = {}
        stale_count = 0
        interview_candidates = 0
        offer_candidates = 0

        for app in apps:
            status_dist[app.status] = status_dist.get(app.status, 0) + 1
            if self._compute_needs_follow_up(app):
                stale_count += 1
            if app.status in ("interview", "offer"):
                interview_candidates += 1
            if app.status == "offer":
                offer_candidates += 1

        interview_rate = (
            round((interview_candidates / total) * 100.0, 2) if total > 0 else 0.0
        )
        offer_rate = (
            round((offer_candidates / interview_candidates) * 100.0, 2)
            if interview_candidates > 0
            else 0.0
        )

        # Média de pontuação de match dos currículos gerados
        stmt_resumes = select(func.avg(GeneratedResume.match_percentage)).where(
            GeneratedResume.user_id == user.id
        )
        res_avg = await self.db.execute(stmt_resumes)
        avg_score = res_avg.scalar() or 0.0

        return ApplicationAnalyticsMetrics(
            total_applications=total,
            status_distribution=status_dist,
            stale_applications_count=stale_count,
            interview_conversion_rate=interview_rate,
            offer_conversion_rate=offer_rate,
            average_match_score=round(float(avg_score), 2),
        )
