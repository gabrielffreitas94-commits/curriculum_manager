"""Testes unitários para o ApplicationService (ATS Core e ciclo de vida de candidaturas).

Valida lógica de estagnação (>7 dias), transições de etapas, contatos, notas,
métricas analíticas com divisão por zero e isolamento multi-tenant.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.application import (
    ApplicationContactCreate,
    ApplicationCreate,
    ApplicationNoteCreate,
    ApplicationStageCreate,
    ApplicationStageUpdate,
    ApplicationUpdate,
)
from app.domain.models import Application, User
from app.services.application_service import ApplicationService


@pytest.fixture
def test_user() -> User:
    """Fixture com usuário do domínio para testes unitários."""
    return User(
        id=uuid.uuid4(),
        firebase_uid="unit_test_user_uid",
        email="test_app_service@thothcvs.ai",
        full_name="Unit Tester",
    )


def test_compute_needs_follow_up_logic() -> None:
    """Valida as regras de negócio puras para detecção de follow-up proativo."""
    service = ApplicationService(db=None)  # type: ignore[arg-type]

    # 1. reminder_active = False nunca precisa de follow-up
    app_inactive = Application(
        reminder_active=False,
        status="applied",
        last_activity_at=datetime.now(UTC) - timedelta(days=10),
    )
    assert service._compute_needs_follow_up(app_inactive) is False

    # 2. Status finais nunca precisam de follow-up
    for final_status in ("rejected", "offer", "withdrawn"):
        app_final = Application(
            reminder_active=True,
            status=final_status,
            last_activity_at=datetime.now(UTC) - timedelta(days=20),
        )
        assert service._compute_needs_follow_up(app_final) is False

    # 3. Candidatura recente (< 7 dias)
    app_recent = Application(
        reminder_active=True,
        status="applied",
        last_activity_at=datetime.now(UTC) - timedelta(days=3),
    )
    assert service._compute_needs_follow_up(app_recent) is False

    # 4. Candidatura estagnada (> 7 dias)
    app_stale = Application(
        reminder_active=True,
        status="applied",
        last_activity_at=datetime.now(UTC) - timedelta(days=8),
    )
    assert service._compute_needs_follow_up(app_stale) is True

    # 5. Data ingênua (naive datetime sem tzinfo)
    naive_date = datetime.now() - timedelta(days=9)
    app_naive = Application(
        reminder_active=True,
        status="interview",
        last_activity_at=naive_date,
    )
    assert service._compute_needs_follow_up(app_naive) is True


@pytest.mark.asyncio
async def test_crud_and_lifecycle_application_service(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Testa criação, listagem filtrada, detalhamento, atualização e soft delete."""
    db_session.add(test_user)
    await db_session.flush()

    service = ApplicationService(db=db_session)

    # 1. Create
    payload = ApplicationCreate(
        company_name="Acme Tech",
        job_title="Senior Python Engineer",
        job_description="Requisitos FastAPI",
        work_model="remote",
        status="applied",
    )
    app_item = await service.create_application(user=test_user, payload=payload)
    assert app_item.id is not None
    assert app_item.company_name == "Acme Tech"

    # 2. List com filtros
    apps_all = await service.list_applications(user=test_user)
    assert len(apps_all) == 1

    apps_filter_status = await service.list_applications(user=test_user, status_filter="applied")
    assert len(apps_filter_status) == 1

    apps_filter_none = await service.list_applications(user=test_user, status_filter="offer")
    assert len(apps_filter_none) == 0

    apps_filter_follow_up = await service.list_applications(user=test_user, needs_follow_up=True)
    assert len(apps_filter_follow_up) == 0

    # 3. Get Detail
    detail = await service.get_application_detail(user=test_user, app_id=app_item.id)
    assert detail.company_name == "Acme Tech"
    assert len(detail.stages) == 0

    # 4. Update
    update_payload = ApplicationUpdate(job_title="Lead Architect", status="interview")
    updated_item = await service.update_application(
        user=test_user, app_id=app_item.id, payload=update_payload
    )
    assert updated_item.job_title == "Lead Architect"
    assert updated_item.status == "interview"

    # 5. Soft Delete
    await service.delete_application(user=test_user, app_id=app_item.id)
    apps_after_delete = await service.list_applications(user=test_user)
    assert len(apps_after_delete) == 0


@pytest.mark.asyncio
async def test_application_service_not_found_errors(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Garante que IDs inexistentes levantem HTTPException 404 em todas as operações."""
    db_session.add(test_user)
    await db_session.flush()

    service = ApplicationService(db=db_session)
    random_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_detail:
        await service.get_application_detail(user=test_user, app_id=random_id)
    assert exc_detail.value.status_code == 404

    with pytest.raises(HTTPException) as exc_update:
        await service.update_application(
            user=test_user, app_id=random_id, payload=ApplicationUpdate()
        )
    assert exc_update.value.status_code == 404

    with pytest.raises(HTTPException) as exc_delete:
        await service.delete_application(user=test_user, app_id=random_id)
    assert exc_delete.value.status_code == 404


@pytest.mark.asyncio
async def test_stages_contacts_and_notes_service(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Testa adição e atualização de estágios, contatos e notas."""
    db_session.add(test_user)
    await db_session.flush()

    service = ApplicationService(db=db_session)
    app_item = await service.create_application(
        user=test_user,
        payload=ApplicationCreate(
            company_name="FinTech Hub",
            job_title="Backend Lead",
            job_description="Sistemas distribuídos",
        ),
    )

    # 1. Add Stage
    stage = await service.add_stage(
        user=test_user,
        app_id=app_item.id,
        payload=ApplicationStageCreate(stage_name="Entrevista RH", order_index=1),
    )
    assert stage.stage_name == "Entrevista RH"

    # Update Stage
    updated_stage = await service.update_stage(
        user=test_user,
        app_id=app_item.id,
        stage_id=stage.id,
        payload=ApplicationStageUpdate(status="completed", feedback_notes="Muito positivo"),
    )
    assert updated_stage.status == "completed"

    # 2. Add Contact com fallbacks de nome e role
    contact = await service.add_contact(
        user=test_user,
        app_id=app_item.id,
        payload=ApplicationContactCreate(name="Paula Recruiter", role="HR Lead"),
    )
    assert contact.name == "Paula Recruiter"
    assert contact.role == "HR Lead"

    # 3. Add Note
    note = await service.add_note(
        user=test_user,
        app_id=app_item.id,
        payload=ApplicationNoteCreate(
            content="Estudar algoritmos de fila", note_type="interview_prep"
        ),
    )
    assert note.content == "Estudar algoritmos de fila"


@pytest.mark.asyncio
async def test_analytics_metrics_empty_and_populated(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Garante cálculo correto de taxas e prevenção de divisão por zero."""
    db_session.add(test_user)
    await db_session.flush()

    service = ApplicationService(db=db_session)

    # 1. Usuário sem nenhuma candidatura cadastrada
    metrics_empty = await service.get_analytics_metrics(user=test_user)
    assert metrics_empty.total_applications == 0
    assert metrics_empty.interview_conversion_rate == 0.0
    assert metrics_empty.offer_conversion_rate == 0.0
    assert metrics_empty.average_match_score == 0.0

    # 2. Cadastra candidaturas para aferir conversão
    await service.create_application(
        user=test_user,
        payload=ApplicationCreate(
            company_name="C1", job_title="Dev", job_description="d", status="interview"
        ),
    )
    await service.create_application(
        user=test_user,
        payload=ApplicationCreate(
            company_name="C2", job_title="Dev", job_description="d", status="offer"
        ),
    )
    await service.create_application(
        user=test_user,
        payload=ApplicationCreate(
            company_name="C3", job_title="Dev", job_description="d", status="applied"
        ),
    )

    metrics_populated = await service.get_analytics_metrics(user=test_user)
    assert metrics_populated.total_applications == 3
    # 2 entrevistadas (interview + offer) de 3 total -> 66.67%
    assert metrics_populated.interview_conversion_rate == 66.67
    # 1 proposta de 2 entrevistadas -> 50.0%
    assert metrics_populated.offer_conversion_rate == 50.0
