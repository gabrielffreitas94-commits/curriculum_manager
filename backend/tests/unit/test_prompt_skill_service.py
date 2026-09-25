"""Testes unitários para o PromptSkillService."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PromptSkill, User
from app.services.prompt_skill_service import SYSTEM_PROMPT_SKILLS, PromptSkillService


@pytest.mark.asyncio
async def test_ensure_system_prompt_skills_seeds_and_is_idempotent(
    db_session: AsyncSession,
) -> None:
    """Valida a semeadura das 5 metodologias padrão e a idempotência em execuções subsequentes."""
    service = PromptSkillService(db_session)

    # 1. Primeira execução: deve semear as 5 skills
    skills_first_run = await service.ensure_system_prompt_skills()
    assert len(skills_first_run) == len(SYSTEM_PROMPT_SKILLS)
    slugs = {s.slug for s in skills_first_run}
    assert "google-xyz" in slugs
    assert "star-method" in slugs
    assert "tech-startup" in slugs
    assert "enterprise-gov" in slugs
    assert "executive-leadership" in slugs

    # 2. Segunda execução: não deve criar duplicatas
    skills_second_run = await service.ensure_system_prompt_skills()
    assert len(skills_second_run) == len(SYSTEM_PROMPT_SKILLS)


@pytest.mark.asyncio
async def test_list_active_skills_with_user_and_custom_skills(
    db_session: AsyncSession,
) -> None:
    """Valida listagem de skills ativas, incluindo as customizadas do usuário."""
    service = PromptSkillService(db_session)
    await service.ensure_system_prompt_skills()

    user = User(
        firebase_uid="test-user-skills-uid",
        email="test_skills@example.com",
        full_name="Usuario Skills Teste",
    )
    db_session.add(user)
    await db_session.commit()

    other_user_id = uuid.uuid4()

    # Cria uma skill customizada do usuário atual
    custom_skill = PromptSkill(
        slug="my-custom-skill",
        name="Minha Skill Customizada",
        description="Foco em bioinformática e ML",
        category="tech",
        system_prompt="Destaque publicações e pipelines.",
        default_language="pt-BR",
        is_system_default=False,
        created_by_user_id=user.id,
        is_active=True,
    )
    # Cria uma skill de outro usuário
    other_user_skill = PromptSkill(
        slug="other-user-skill",
        name="Skill de Outro Usuário",
        description="Privada",
        category="general",
        system_prompt="Ignorar.",
        default_language="pt-BR",
        is_system_default=False,
        created_by_user_id=other_user_id,
        is_active=True,
    )
    # Cria uma skill inativa do usuário
    inactive_skill = PromptSkill(
        slug="inactive-skill",
        name="Skill Inativa",
        description="Inativa",
        category="general",
        system_prompt="Ignorar.",
        default_language="pt-BR",
        is_system_default=False,
        created_by_user_id=user.id,
        is_active=False,
    )
    db_session.add_all([custom_skill, other_user_skill, inactive_skill])
    await db_session.commit()

    # Listagem para o test_user
    skills = await service.list_active_skills(user_id=user.id)
    skill_slugs = [s.slug for s in skills]

    assert "google-xyz" in skill_slugs
    assert "my-custom-skill" in skill_slugs
    assert "other-user-skill" not in skill_slugs
    assert "inactive-skill" not in skill_slugs

    # Listagem anônima (sem user_id)
    anon_skills = await service.list_active_skills(user_id=None)
    anon_slugs = [s.slug for s in anon_skills]
    assert "google-xyz" in anon_slugs
    assert "my-custom-skill" not in anon_slugs


@pytest.mark.asyncio
async def test_get_by_slug(db_session: AsyncSession) -> None:
    """Valida busca por slug existente e inexistente."""
    service = PromptSkillService(db_session)
    await service.ensure_system_prompt_skills()

    skill = await service.get_by_slug("google-xyz")
    assert skill is not None
    assert skill.name == "Fórmula Google XYZ"
    assert skill.category == "tech"

    non_existent = await service.get_by_slug("non-existent-slug-xyz")
    assert non_existent is None
