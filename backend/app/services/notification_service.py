"""Serviço de gerenciamento de notificações e varredura de follow-ups do ATS.

Implementa a persistência, contagem de pendências, leitura em lote e
o motor proativo de identificação de candidaturas estagnadas (> 7 dias).
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.notification import NotificationResponse
from app.domain.models import Application, Notification, User

FOLLOW_UP_INTERVAL_DAYS = 7


class NotificationService:
    """Orquestrador das notificações in-app e alertas automatizados do sistema."""

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o serviço com a sessão ativa de banco de dados.

        Args:
            db: Sessão ativa do SQLAlchemy AsyncSession.
        """
        self.db = db

    async def list_notifications(
        self,
        user: User,
        unread_only: bool = False,
    ) -> list[NotificationResponse]:
        """Lista as notificações registradas para o usuário.

        Args:
            user: Usuário autenticado proprietário.
            unread_only: Se True, filtra apenas notificações com is_read=False.

        Returns:
            Lista ordenada por data de criação decrescente.
        """
        stmt = (
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
        )
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))

        result = await self.db.execute(stmt)
        notifs = result.scalars().all()
        return [NotificationResponse.model_validate(n) for n in notifs]

    async def get_unread_count(self, user: User) -> int:
        """Calcula a contagem de notificações não lidas pelo usuário.

        Args:
            user: Usuário proprietário.

        Returns:
            Número inteiro de notificações pendentes.
        """
        stmt = (
            select(func.count(Notification.id))
            .where(
                Notification.user_id == user.id,
                Notification.is_read.is_(False),
            )
        )
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def mark_as_read(
        self,
        user: User,
        notification_id: uuid.UUID,
    ) -> NotificationResponse:
        """Marca uma notificação individual como lida.

        Args:
            user: Usuário proprietário.
            notification_id: UUID da notificação alvo.

        Returns:
            NotificationResponse atualizado.

        Raises:
            HTTPException: 404 caso não pertença ao usuário ou não exista.
        """
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
        result = await self.db.execute(stmt)
        notif = result.scalar_one_or_none()

        if not notif:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notificação não encontrada ou não pertence ao usuário.",
            )

        notif.is_read = True
        await self.db.commit()
        await self.db.refresh(notif)
        return NotificationResponse.model_validate(notif)

    async def mark_all_as_read(self, user: User) -> int:
        """Marca em lote todas as notificações pendentes do usuário como lidas.

        Args:
            user: Usuário proprietário.

        Returns:
            Quantidade de registros atualizados.
        """
        stmt = (
            update(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        row_count = getattr(result, "rowcount", 0)
        return int(row_count or 0)

    async def scan_and_generate_follow_ups(self, user: User) -> int:
        """Varre candidaturas estagnadas e gera lembretes proativos de follow-up.

        Regras:
            - Considera apenas vagas com reminder_active=True e status em andamento.
            - Verifica se last_activity_at é anterior a 7 dias atrás.
            - Evita duplicação se já existir um lembrete não lido para a mesma vaga.

        Args:
            user: Usuário candidato autenticado.

        Returns:
            Quantidade de novas notificações criadas.
        """
        threshold = datetime.now(UTC) - timedelta(days=FOLLOW_UP_INTERVAL_DAYS)
        stmt = (
            select(Application)
            .where(
                Application.user_id == user.id,
                Application.deleted_at.is_(None),
                Application.reminder_active.is_(True),
                Application.status.not_in(["rejected", "offer", "withdrawn"]),
                Application.last_activity_at <= threshold,
            )
        )
        result = await self.db.execute(stmt)
        stale_apps = result.scalars().all()

        created_count = 0
        for app in stale_apps:
            # Verifica se já existe lembrete não lido ativo para a mesma vaga
            stmt_existing = select(Notification).where(
                Notification.user_id == user.id,
                Notification.application_id == app.id,
                Notification.notification_type == "follow_up_reminder",
                Notification.is_read.is_(False),
            )
            existing = await self.db.execute(stmt_existing)
            if existing.scalar_one_or_none() is not None:
                continue

            notif = Notification(
                user_id=user.id,
                application_id=app.id,
                notification_type="follow_up_reminder",
                title=f"Lembrete de Follow-up: {app.company_name}",
                message=(
                    f"Mais de 7 dias se passaram desde o último contato sobre a vaga de "
                    f"'{app.job_title}' na empresa {app.company_name}. "
                    "Considere enviar uma mensagem cordial de acompanhamento ao recrutador."
                ),
                is_read=False,
                scheduled_for=datetime.now(UTC),
                sent_at=datetime.now(UTC),
            )
            self.db.add(notif)
            created_count += 1

        if created_count > 0:
            await self.db.commit()

        return created_count
