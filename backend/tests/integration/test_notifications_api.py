"""Testes de integração para o sistema de notificações e lembretes proativos do ATS.

Valida a consulta de alertas, contagem de não lidas, marcação de leitura individual
e em lote, disparo da varredura de candidaturas estagnadas (>7 dias) e isolamento multi-tenant.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Application, Notification, User
from app.ports.auth_port import AuthUser

USER_A_ID = uuid.uuid4()
USER_B_ID = uuid.uuid4()

AUTH_USER_A = AuthUser(
    uid="user_notif_a",
    email="notif_user_a@example.com",
    full_name="Notif User A",
)

AUTH_USER_B = AuthUser(
    uid="user_notif_b",
    email="notif_user_b@example.com",
    full_name="Notif User B",
)


@pytest.fixture
async def setup_notif_users(db_session: AsyncSession) -> dict:
    """Configura usuários de teste e notificações iniciais."""
    user_a = User(
        id=USER_A_ID,
        firebase_uid="user_notif_a",
        email="notif_user_a@example.com",
        full_name="Notif User A",
    )
    user_b = User(
        id=USER_B_ID,
        firebase_uid="user_notif_b",
        email="notif_user_b@example.com",
        full_name="Notif User B",
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()

    return {
        "user_a_id": str(USER_A_ID),
        "user_b_id": str(USER_B_ID),
        "headers_a": {"Authorization": "Bearer token_a"},
        "headers_b": {"Authorization": "Bearer token_b"},
    }


@pytest.mark.asyncio
async def test_list_notifications_and_unread_count(
    async_client: AsyncClient,
    setup_notif_users: dict,
    db_session: AsyncSession,
) -> None:
    """Valida a listagem de notificações com filtro de não lidas e contagem precisa."""
    headers = setup_notif_users["headers_a"]
    user_id = uuid.UUID(setup_notif_users["user_a_id"])

    n1 = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        notification_type="follow_up_reminder",
        title="Lembrete de Follow-up",
        message="Faça contato com a Acme Corp.",
        is_read=False,
    )
    n2 = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        notification_type="system",
        title="Boas-vindas ao ThothCVs AI",
        message="Seu perfil está pronto para gerar currículos.",
        is_read=True,
    )
    db_session.add_all([n1, n2])
    await db_session.commit()

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_A):
        # 1. Contagem de não lidas
        res_count = await async_client.get(
            "/api/v1/notifications/unread-count",
            headers=headers,
        )
        assert res_count.status_code == 200
        assert res_count.json()["unread_count"] == 1

        # 2. Listagem de todas
        res_all = await async_client.get("/api/v1/notifications", headers=headers)
        assert res_all.status_code == 200
        items_all = res_all.json()
        assert len(items_all) == 2

        # 3. Listagem apenas não lidas
        res_unread = await async_client.get(
            "/api/v1/notifications?unread_only=true",
            headers=headers,
        )
        assert res_unread.status_code == 200
        items_unread = res_unread.json()
        assert len(items_unread) == 1
        assert items_unread[0]["title"] == "Lembrete de Follow-up"


@pytest.mark.asyncio
async def test_mark_notification_as_read(
    async_client: AsyncClient,
    setup_notif_users: dict,
    db_session: AsyncSession,
) -> None:
    """Garante que a notificação possa ser marcada como lida individualmente."""
    headers = setup_notif_users["headers_a"]
    user_id = uuid.UUID(setup_notif_users["user_a_id"])

    notif = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        notification_type="interview_alert",
        title="Entrevista Agendada",
        message="Você tem entrevista amanhã.",
        is_read=False,
    )
    db_session.add(notif)
    await db_session.commit()

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_A):
        res_mark = await async_client.patch(
            f"/api/v1/notifications/{notif.id}/read",
            headers=headers,
        )
        assert res_mark.status_code == 200
        assert res_mark.json()["is_read"] is True

        res_count = await async_client.get(
            "/api/v1/notifications/unread-count",
            headers=headers,
        )
        assert res_count.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_mark_all_notifications_read(
    async_client: AsyncClient,
    setup_notif_users: dict,
    db_session: AsyncSession,
) -> None:
    """Valida a marcação em lote de todas as notificações não lidas."""
    headers = setup_notif_users["headers_a"]
    user_id = uuid.UUID(setup_notif_users["user_a_id"])

    for i in range(3):
        db_session.add(
            Notification(
                id=uuid.uuid4(),
                user_id=user_id,
                notification_type="follow_up_reminder",
                title=f"Lembrete {i}",
                message="Mensagem de teste.",
                is_read=False,
            )
        )
    await db_session.commit()

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_A):
        res_all = await async_client.post(
            "/api/v1/notifications/mark-all-read",
            headers=headers,
        )
        assert res_all.status_code == 200
        assert res_all.json()["updated_count"] >= 3

        res_count = await async_client.get(
            "/api/v1/notifications/unread-count",
            headers=headers,
        )
        assert res_count.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_scan_follow_ups_generates_notifications(
    async_client: AsyncClient,
    setup_notif_users: dict,
    db_session: AsyncSession,
) -> None:
    """Garante que a varredura proativa crie alertas para vagas sem resposta há > 7 dias."""
    headers = setup_notif_users["headers_a"]
    user_id = uuid.UUID(setup_notif_users["user_a_id"])

    # Cria candidatura parada há 9 dias
    stale_app = Application(
        id=uuid.uuid4(),
        user_id=user_id,
        company_name="Spotify",
        job_title="Backend Engineer",
        job_description="Requisitos da vaga.",
        status="applied",
        last_activity_at=datetime.now(UTC) - timedelta(days=9),
        reminder_active=True,
    )
    db_session.add(stale_app)
    await db_session.commit()

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_A):
        # 1. Dispara a varredura
        res_scan = await async_client.post(
            "/api/v1/notifications/scan-follow-ups",
            headers=headers,
        )
        assert res_scan.status_code == 200
        assert res_scan.json()["created_count"] == 1

        # 2. Confirma se a notificação foi gerada
        res_list = await async_client.get("/api/v1/notifications", headers=headers)
        items = res_list.json()
        assert any("Spotify" in it["title"] or "Spotify" in it["message"] for it in items)

        # 3. Disparar novamente não deve duplicar o alerta não lido
        res_scan_again = await async_client.post(
            "/api/v1/notifications/scan-follow-ups",
            headers=headers,
        )
        assert res_scan_again.status_code == 200
        assert res_scan_again.json()["created_count"] == 0


@pytest.mark.asyncio
async def test_notification_tenant_isolation(
    async_client: AsyncClient,
    setup_notif_users: dict,
    db_session: AsyncSession,
) -> None:
    """
    VETOR DE AMEAÇA: CWE-639 / CWE-284 (Broken Object Level Authorization / IDOR).
    Um usuário autenticado (User B) tenta inspecionar ou alterar o estado de notificações
    privadas pertencentes a outro usuário (User A).

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    O sistema DEVE retornar HTTP 404 (Not Found) ao tentar marcar como lida uma notificação
    que pertença a outro usuário, preservando o sigilo de alertas e status de candidaturas.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Um desenvolvedor ou IA pode consultar a notificação no repositório filtrando apenas por 'id'
    sem validar a cláusula 'user_id == current_user.id', reintroduzindo vazamento BOLA/IDOR.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    A tentativa do User B de interagir com 'notif_a.id' deve retornar status 404 estrito.
    """
    headers_b = setup_notif_users["headers_b"]
    user_a_id = uuid.UUID(setup_notif_users["user_a_id"])

    notif_a = Notification(
        id=uuid.uuid4(),
        user_id=user_a_id,
        notification_type="follow_up_reminder",
        title="Alerta Privado",
        message="Segredo do User A",
        is_read=False,
    )
    db_session.add(notif_a)
    await db_session.commit()

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_B):
        res = await async_client.patch(
            f"/api/v1/notifications/{notif_a.id}/read",
            headers=headers_b,
        )
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_mark_notification_not_found_raises_404(
    async_client: AsyncClient,
    setup_notif_users: dict,
) -> None:
    """Garante 404 ao tentar marcar como lida notificação inexistente."""
    headers_a = setup_notif_users["headers_a"]
    fake_notif_id = uuid.uuid4()

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_A):
        res = await async_client.patch(
            f"/api/v1/notifications/{fake_notif_id}/read",
            headers=headers_a,
        )
        assert res.status_code == 404
