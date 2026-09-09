"""Testes de integração para o ATS Core e ciclo de vida de candidaturas.

Valida a criação, transições de status no funil Kanban, gestão de etapas dinâmicas,
adicionamento de contatos e notas, algoritmo de detecção de follow-up proativo (7 dias)
e métricas agregadas de conversão para o usuário candidato.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Application, User
from app.ports.auth_port import AuthUser

USER_A_ID = uuid.uuid4()
USER_B_ID = uuid.uuid4()

AUTH_USER_A = AuthUser(
    uid="user_ats_a",
    email="ats_user_a@example.com",
    full_name="ATS User A",
)

AUTH_USER_B = AuthUser(
    uid="user_ats_b",
    email="ats_user_b@example.com",
    full_name="ATS User B",
)


@pytest.fixture
async def setup_ats_users(db_session: AsyncSession) -> dict:
    """Configura usuários candidatos no banco para isolamento de tenant."""
    user_a = User(
        id=USER_A_ID,
        firebase_uid="user_ats_a",
        email="ats_user_a@example.com",
        full_name="ATS User A",
    )
    user_b = User(
        id=USER_B_ID,
        firebase_uid="user_ats_b",
        email="ats_user_b@example.com",
        full_name="ATS User B",
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
async def test_create_and_list_application(
    async_client: AsyncClient,
    setup_ats_users: dict,
) -> None:
    """Garante o cadastro e listagem de candidaturas no funil ATS."""
    headers = setup_ats_users["headers_a"]

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_A):
        create_payload = {
            "company_name": "Stripe",
            "job_title": "Senior Backend Engineer",
            "job_url": "https://stripe.com/jobs/123",
            "job_description": "Desenvolvimento de APIs resilientes com Python e Go.",
            "work_model": "remote",
            "salary_range": "$120k - $150k",
            "location": "Remoto (Brasil)",
            "status": "applied",
        }

        res = await async_client.post(
            "/api/v1/applications",
            headers=headers,
            json=create_payload,
        )
        assert res.status_code == 201
        app_data = res.json()
        assert app_data["id"] is not None
        assert app_data["company_name"] == "Stripe"
        assert app_data["status"] == "applied"
        assert app_data["needs_follow_up"] is False

        # Listagem
        res_list = await async_client.get("/api/v1/applications", headers=headers)
        assert res_list.status_code == 200
        items = res_list.json()
        assert len(items) >= 1
        assert any(it["company_name"] == "Stripe" for it in items)


@pytest.mark.asyncio
async def test_stages_contacts_and_notes_flow(
    async_client: AsyncClient,
    setup_ats_users: dict,
) -> None:
    """Testa adição de etapas de processo seletivo, contatos de recrutador e notas."""
    headers = setup_ats_users["headers_a"]

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_A):
        # 1. Cria candidatura base
        res_app = await async_client.post(
            "/api/v1/applications",
            headers=headers,
            json={
                "company_name": "Nubank",
                "job_title": "Tech Lead Python",
                "job_description": "Liderança técnica e arquitetura de microsserviços.",
                "status": "applied",
            },
        )
        assert res_app.status_code == 201
        app_id = res_app.json()["id"]

        # 2. Adiciona Etapa Seletiva
        res_stage = await async_client.post(
            f"/api/v1/applications/{app_id}/stages",
            headers=headers,
            json={
                "stage_name": "Live Coding & System Design",
                "order_index": 1,
                "status": "pending",
                "scheduled_at": "2026-10-15T14:00:00Z",
            },
        )
        assert res_stage.status_code == 201
        stage_data = res_stage.json()
        assert stage_data["stage_name"] == "Live Coding & System Design"
        stage_id = stage_data["id"]

        # Atualiza a etapa para 'completed'
        res_update_stage = await async_client.patch(
            f"/api/v1/applications/{app_id}/stages/{stage_id}",
            headers=headers,
            json={"status": "completed", "feedback_notes": "Aprovado com elogios no design."},
        )
        assert res_update_stage.status_code == 200
        assert res_update_stage.json()["status"] == "completed"

        # 3. Adiciona Contato de Recrutamento
        res_contact = await async_client.post(
            f"/api/v1/applications/{app_id}/contacts",
            headers=headers,
            json={
                "name": "Mariana Tech Recruiter",
                "role": "Lead Talent Acquisition",
                "email": "mariana@nubank.com.br",
                "phone": "+55 11 97777-6666",
            },
        )
        assert res_contact.status_code == 201
        assert res_contact.json()["name"] == "Mariana Tech Recruiter"

        # 4. Adiciona Nota
        res_note = await async_client.post(
            f"/api/v1/applications/{app_id}/notes",
            headers=headers,
            json={
                "content": "Revisar algoritmos de concorrência e partição no Kafka.",
                "note_type": "interview_prep",
            },
        )
        assert res_note.status_code == 201
        assert res_note.json()["note_type"] == "interview_prep"

        # 5. Obtém a candidatura detalhada
        res_detail = await async_client.get(
            f"/api/v1/applications/{app_id}",
            headers=headers,
        )
        assert res_detail.status_code == 200
        detail = res_detail.json()
        assert len(detail["stages"]) == 1
        assert len(detail["contacts"]) == 1
        assert len(detail["notes"]) == 1


@pytest.mark.asyncio
async def test_stale_application_follow_up_detector(
    async_client: AsyncClient,
    setup_ats_users: dict,
    db_session: AsyncSession,
) -> None:
    """Garante que candidaturas paradas há mais de 7 dias acionem o alerta de follow-up."""
    headers = setup_ats_users["headers_a"]
    user_id = uuid.UUID(setup_ats_users["user_a_id"])

    # Cria candidatura com last_activity_at de 8 dias atrás
    stale_app = Application(
        id=uuid.uuid4(),
        user_id=user_id,
        company_name="Stale Inc",
        job_title="Software Engineer",
        job_description="Descrição de teste.",
        status="applied",
        last_activity_at=datetime.now(UTC) - timedelta(days=8),
        reminder_active=True,
    )
    db_session.add(stale_app)
    await db_session.commit()

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_A):
        res = await async_client.get(
            f"/api/v1/applications/{stale_app.id}",
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["needs_follow_up"] is True

        # Listagem com filtro needs_follow_up=true
        res_filtered = await async_client.get(
            "/api/v1/applications?needs_follow_up=true",
            headers=headers,
        )
        assert res_filtered.status_code == 200
        items = res_filtered.json()
        assert any(it["id"] == str(stale_app.id) for it in items)


@pytest.mark.asyncio
async def test_applications_analytics_metrics(
    async_client: AsyncClient,
    setup_ats_users: dict,
    db_session: AsyncSession,
) -> None:
    """Valida as métricas de funil, conversão em entrevistas e propostas do candidato."""
    headers = setup_ats_users["headers_a"]
    user_id = uuid.UUID(setup_ats_users["user_a_id"])

    apps = [
        Application(
            user_id=user_id,
            company_name="Company 1",
            job_title="Dev",
            job_description="Desc",
            status="applied",
        ),
        Application(
            user_id=user_id,
            company_name="Company 2",
            job_title="Dev",
            job_description="Desc",
            status="interview",
        ),
        Application(
            user_id=user_id,
            company_name="Company 3",
            job_title="Dev",
            job_description="Desc",
            status="offer",
        ),
    ]
    db_session.add_all(apps)
    await db_session.commit()

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_A):
        res = await async_client.get(
            "/api/v1/applications/analytics/metrics",
            headers=headers,
        )
        assert res.status_code == 200
        metrics = res.json()
        assert metrics["total_applications"] >= 3
        assert metrics["status_distribution"]["applied"] >= 1
        assert metrics["status_distribution"]["interview"] >= 1
        assert metrics["status_distribution"]["offer"] >= 1
        assert "interview_conversion_rate" in metrics
        assert "offer_conversion_rate" in metrics


@pytest.mark.asyncio
async def test_application_tenant_isolation(
    async_client: AsyncClient,
    setup_ats_users: dict,
) -> None:
    """Garante que o User B receba 404 ao tentar acessar ou alterar candidatura do User A."""
    headers_a = setup_ats_users["headers_a"]
    headers_b = setup_ats_users["headers_b"]

    # User A cria
    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_A):
        res_create = await async_client.post(
            "/api/v1/applications",
            headers=headers_a,
            json={
                "company_name": "Private Corp A",
                "job_title": "Confidential Role",
                "job_description": "Dados sigilosos.",
                "status": "applied",
            },
        )
        assert res_create.status_code == 201
        app_id = res_create.json()["id"]

    # User B tenta acessar -> 404
    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER_B):
        res_get = await async_client.get(
            f"/api/v1/applications/{app_id}",
            headers=headers_b,
        )
        assert res_get.status_code == 404

        res_patch = await async_client.patch(
            f"/api/v1/applications/{app_id}",
            headers=headers_b,
            json={"company_name": "Hacked Name"},
        )
        assert res_patch.status_code == 404

        res_delete = await async_client.delete(
            f"/api/v1/applications/{app_id}",
            headers=headers_b,
        )
        assert res_delete.status_code == 404
