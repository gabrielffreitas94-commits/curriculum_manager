"""Testes unitários para o NotificationService (Alertas e varredura de follow-ups do ATS).

Valida listagem com filtro unread, contadores, marcação individual e em lote,
além do motor de varredura proativo anti-duplicação.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Application, Notification, User
from app.services.notification_service import NotificationService


@pytest.fixture
def notif_user() -> User:
    """Fixture com usuário para teste de notificações."""
    return User(
        id=uuid.uuid4(),
        firebase_uid="notif_user_uid_123",
        email="notif_service@thothcvs.ai",
        full_name="Notif Service Tester",
    )


@pytest.mark.asyncio
async def test_notification_service_list_and_read_flows(
    db_session: AsyncSession,
    notif_user: User,
) -> None:
    """Valida consulta de notificações, contagem de não lidas e marcações de leitura."""
    db_session.add(notif_user)
    await db_session.flush()

    service = NotificationService(db=db_session)
    user_id = notif_user.id

    # 1. Contagem inicial limpa
    assert await service.get_unread_count(user=notif_user) == 0

    # 2. Adiciona notificações (uma não lida e uma lida)
    n1 = Notification(
        user_id=user_id,
        notification_type="system",
        title="Bem-vindo",
        message="Configurações prontas",
        is_read=False,
    )
    n2 = Notification(
        user_id=user_id,
        notification_type="follow_up_reminder",
        title="Lembrete",
        message="Follow up necessário",
        is_read=True,
    )
    db_session.add_all([n1, n2])
    await db_session.commit()

    # 3. Listagem e contagem
    assert await service.get_unread_count(user=notif_user) == 1
    all_notifs = await service.list_notifications(user=notif_user, unread_only=False)
    assert len(all_notifs) == 2

    unread_notifs = await service.list_notifications(user=notif_user, unread_only=True)
    assert len(unread_notifs) == 1
    assert unread_notifs[0].title == "Bem-vindo"

    # 4. Marcar individual como lida
    read_resp = await service.mark_as_read(user=notif_user, notification_id=n1.id)
    assert read_resp.is_read is True
    assert await service.get_unread_count(user=notif_user) == 0

    # 5. Marcar individual inexistente levanta 404
    with pytest.raises(HTTPException) as exc:
        await service.mark_as_read(user=notif_user, notification_id=uuid.uuid4())
    assert exc.value.status_code == 404

    # 6. Marcar todas como lidas em lote
    n3 = Notification(
        user_id=user_id, notification_type="system", title="N3", message="M3", is_read=False
    )
    n4 = Notification(
        user_id=user_id, notification_type="system", title="N4", message="M4", is_read=False
    )
    db_session.add_all([n3, n4])
    await db_session.commit()

    updated = await service.mark_all_as_read(user=notif_user)
    assert updated >= 2
    assert await service.get_unread_count(user=notif_user) == 0


@pytest.mark.asyncio
async def test_scan_and_generate_follow_ups_deduplication(
    db_session: AsyncSession,
    notif_user: User,
) -> None:
    """Valida que a varredura gera alertas e não duplica lembretes para a mesma vaga."""
    db_session.add(notif_user)
    await db_session.flush()

    service = NotificationService(db=db_session)
    user_id = notif_user.id

    # Cria candidatura parada há 10 dias com reminder_active=True
    stale_app = Application(
        user_id=user_id,
        company_name="Netflix",
        job_title="Senior Engineer",
        job_description="Desc",
        status="interview",
        reminder_active=True,
        last_activity_at=datetime.now(UTC) - timedelta(days=10),
    )
    # Cria candidatura parada há 12 dias mas com reminder_active=False (deve ignorar)
    ignored_app = Application(
        user_id=user_id,
        company_name="Ignored Corp",
        job_title="Dev",
        job_description="Desc",
        status="interview",
        reminder_active=False,
        last_activity_at=datetime.now(UTC) - timedelta(days=12),
    )
    # Cria candidatura parada com status rejeitado (deve ignorar)
    rejected_app = Application(
        user_id=user_id,
        company_name="Rejected Corp",
        job_title="Dev",
        job_description="Desc",
        status="rejected",
        reminder_active=True,
        last_activity_at=datetime.now(UTC) - timedelta(days=15),
    )
    db_session.add_all([stale_app, ignored_app, rejected_app])
    await db_session.commit()

    # Primeira varredura: deve criar exatamente 1 notificação (apenas para Netflix)
    created = await service.scan_and_generate_follow_ups(user=notif_user)
    assert created == 1

    # Segunda varredura imediata: lembrete anterior ainda está não lido, deve ignorar (0)
    created_second = await service.scan_and_generate_follow_ups(user=notif_user)
    assert created_second == 0
