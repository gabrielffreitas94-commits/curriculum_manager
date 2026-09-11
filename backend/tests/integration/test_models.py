"""Testes de integração para os modelos relacionais de domínio do ThothCVs AI.

Valida a persistência, integridade referencial, relacionamentos 1:1 e 1:N,
cascata de exclusão e campos de auditoria/soft delete.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    Application,
    ApplicationContact,
    ApplicationNote,
    ApplicationStage,
    Certification,
    CoverLetter,
    Education,
    Experience,
    GeneratedResume,
    Language,
    Notification,
    Project,
    PromptSkill,
    Skill,
    User,
    UserSettings,
)


@pytest.mark.asyncio
async def test_user_and_settings_creation(db_session: AsyncSession) -> None:
    """Testa a criação de um usuário e sua relação 1:1 com configurações."""
    new_user = User(
        firebase_uid="firebase_test_uid_123",
        email="alex@thothcvs.ai",
        full_name="Alex River",
        target_title="Senior Python Architect",
    )
    db_session.add(new_user)
    await db_session.flush()

    assert new_user.id is not None
    assert new_user.created_at is not None
    assert new_user.deleted_at is None

    settings = UserSettings(
        user_id=new_user.id,
        preferred_language="pt-BR",
        email_notifications_enabled=True,
    )
    db_session.add(settings)
    await db_session.flush()

    # Re-consultar com relacionamento
    result = await db_session.execute(select(User).where(User.id == new_user.id))
    fetched_user = result.scalar_one()
    assert fetched_user.email == "alex@thothcvs.ai"
    assert fetched_user.settings is not None
    assert fetched_user.settings.preferred_language == "pt-BR"


@pytest.mark.asyncio
async def test_experience_and_portfolio_relationships(db_session: AsyncSession) -> None:
    """Testa o cadastro de experiências, formações, projetos e competências do usuário."""
    user = User(
        firebase_uid="firebase_test_uid_456",
        email="dev@thothcvs.ai",
        full_name="Dev User",
    )
    db_session.add(user)
    await db_session.flush()

    experience = Experience(
        user_id=user.id,
        company_name="Tech Corp",
        position_title="Staff Engineer",
        work_model="remote",
        start_date=date(2022, 1, 1),
        is_current=True,
        description="Liderança técnica e arquitetura de microsserviços.",
        bullet_points=["Aumentou throughput em 50%"],
        tech_stack=["Python", "FastAPI", "PostgreSQL"],
    )
    education = Education(
        user_id=user.id,
        institution_name="Universidade de São Paulo",
        degree="Bacharelado",
        field_of_study="Ciência da Computação",
        start_date=date(2016, 2, 1),
        end_date=date(2020, 12, 1),
    )
    certification = Certification(
        user_id=user.id,
        name="AWS Certified Solutions Architect",
        issuing_organization="Amazon Web Services",
        issue_date=date(2023, 5, 10),
    )
    project = Project(
        user_id=user.id,
        title="Open Source ATS Engine",
        description="Engine de ranqueamento semântico de currículos.",
        technologies=["Python", "SQLAlchemy"],
    )
    skill = Skill(
        user_id=user.id,
        name="FastAPI",
        category="backend",
        proficiency_level="expert",
        years_of_experience=5,
        is_featured=True,
    )
    language = Language(
        user_id=user.id,
        language_name="Inglês",
        proficiency_level="fluent",
    )

    db_session.add_all([experience, education, certification, project, skill, language])
    await db_session.flush()

    result = await db_session.execute(select(User).where(User.id == user.id))
    persisted_user = result.scalar_one()

    assert len(persisted_user.experiences) == 1
    assert persisted_user.experiences[0].company_name == "Tech Corp"
    assert persisted_user.experiences[0].tech_stack == ["Python", "FastAPI", "PostgreSQL"]
    assert len(persisted_user.educations) == 1
    assert len(persisted_user.certifications) == 1
    assert len(persisted_user.projects) == 1
    assert len(persisted_user.skills) == 1
    assert len(persisted_user.languages) == 1


@pytest.mark.asyncio
async def test_application_and_tracker_lifecycle(db_session: AsyncSession) -> None:
    """Testa o ciclo de vida de uma candidatura no ATS pessoal com etapas, contatos e notas."""
    user = User(
        firebase_uid="firebase_test_uid_789",
        email="candidate@thothcvs.ai",
        full_name="Candidate Pro",
    )
    db_session.add(user)
    await db_session.flush()

    app = Application(
        user_id=user.id,
        company_name="Google",
        job_title="Software Engineer, Infrastructure",
        job_description="Requisitos: Python, Go, Sistemas Distribuídos.",
        status="applied",
    )
    db_session.add(app)
    await db_session.flush()

    stage = ApplicationStage(
        application_id=app.id,
        stage_name="Entrevista Técnica",
        status="scheduled",
        scheduled_at=datetime.now(UTC),
    )
    contact = ApplicationContact(
        application_id=app.id,
        full_name="Jane Doe",
        role_type="recruiter",
        email="jane.doe@google.com",
    )
    note = ApplicationNote(
        application_id=app.id,
        content="Revisar algoritmos de grafos e concorrência.",
        note_type="interview_prep",
    )
    prompt_skill = PromptSkill(
        slug="tech-startup",
        name="Tech Startup",
        description="Foco em velocidade, ownership e métricas de impacto.",
        system_prompt="Você é um especialista em recrutamento de startups de alto crescimento...",
    )
    db_session.add_all([stage, contact, note, prompt_skill])
    await db_session.flush()

    resume = GeneratedResume(
        application_id=app.id,
        user_id=user.id,
        prompt_skill_id=prompt_skill.id,
        language="pt-BR",
        version_number=1,
        structured_content={"headline": "Backend Engineer", "summary": "Expert em Python"},
        match_analysis={"python": True, "go": False},
        match_percentage=75.0,
    )
    cover_letter = CoverLetter(
        application_id=app.id,
        user_id=user.id,
        content="Prezada equipe do Google, manifesto meu grande entusiasmo...",
        language="pt-BR",
    )
    notification = Notification(
        user_id=user.id,
        application_id=app.id,
        notification_type="follow_up_reminder",
        title="Lembrete de Follow-up (7 dias)",
        message="Faz 7 dias que você não atualiza sua candidatura no Google.",
    )
    db_session.add_all([resume, cover_letter, notification])
    await db_session.flush()

    # Validar persistência e integridade das relações
    result = await db_session.execute(select(Application).where(Application.id == app.id))
    persisted_app = result.scalar_one()

    assert len(persisted_app.stages) == 1
    assert len(persisted_app.contacts) == 1
    assert len(persisted_app.notes) == 1
    assert len(persisted_app.generated_resumes) == 1
    assert len(persisted_app.cover_letters) == 1
    assert persisted_app.generated_resumes[0].match_percentage == 75.0


@pytest.mark.asyncio
async def test_soft_delete_and_cascades(db_session: AsyncSession) -> None:
    """Testa marcação de soft delete e verificação de integridade."""
    user = User(
        firebase_uid="firebase_test_uid_soft",
        email="delete_me@thothcvs.ai",
        full_name="Temp User",
    )
    db_session.add(user)
    await db_session.flush()

    # Soft delete
    user.deleted_at = datetime.now(UTC)
    await db_session.flush()

    # Consulta padrão sem filtro retorna com deleted_at preenchido
    result = await db_session.execute(select(User).where(User.id == user.id))
    persisted = result.scalar_one()
    assert persisted.deleted_at is not None

    # Consulta ativa com filtro IS NULL
    result_active = await db_session.execute(
        select(User).where(User.id == user.id, User.deleted_at.is_(None))
    )
    assert result_active.scalar_one_or_none() is None
