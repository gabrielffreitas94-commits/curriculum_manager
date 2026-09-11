"""Testes unitários diretos para os endpoints do router de perfil (/api/v1/profile).

Garante cobertura completa de 100% em todas as branches de retorno e exceções 404
independentemente do mecanismo de tracing ASGI/anyio.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.profile import (
    create_certification,
    create_education,
    create_experience,
    create_language,
    create_project,
    create_skill,
    delete_certification,
    delete_education,
    delete_experience,
    delete_language,
    delete_project,
    delete_skill,
    get_experience,
    get_full_dossier,
    get_profile_service,
    list_certifications,
    list_educations,
    list_experiences,
    list_languages,
    list_projects,
    list_skills,
    update_certification,
    update_education,
    update_experience,
    update_language,
    update_project,
    update_skill,
)
from app.api.v1.schemas.profile import (
    CertificationCreateRequest,
    CertificationUpdateRequest,
    EducationCreateRequest,
    EducationUpdateRequest,
    ExperienceCreateRequest,
    ExperienceUpdateRequest,
    LanguageCreateRequest,
    LanguageUpdateRequest,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    SkillCreateRequest,
    SkillUpdateRequest,
)
from app.domain.models import User


@pytest.fixture
def mock_user() -> User:
    """Fixture de usuário modelo."""
    return User(id=uuid.uuid4(), firebase_uid="test_direct_uid", email="direct@test.com")


@pytest.mark.asyncio
async def test_experience_endpoints_direct(mock_user: User) -> None:
    """Valida branches de sucesso e 404 para experiências."""
    assert get_profile_service(db=MagicMock()) is not None
    service = MagicMock()
    exp_id = uuid.uuid4()

    # Create & List
    service.create_experience = AsyncMock(return_value={"id": exp_id})
    service.list_experiences = AsyncMock(return_value=[{"id": exp_id}])
    await create_experience(
        body=ExperienceCreateRequest(
            company_name="A", position_title="B", start_date="2020-01-01", description="desc"
        ),
        current_user=mock_user,
        service=service,
    )

    await list_experiences(current_user=mock_user, service=service)

    # Get by ID: 200 e 404
    service.get_experience = AsyncMock(return_value={"id": exp_id})
    res_get = await get_experience(experience_id=exp_id, current_user=mock_user, service=service)
    assert res_get == {"id": exp_id}

    service.get_experience = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_get:
        await get_experience(experience_id=exp_id, current_user=mock_user, service=service)
    assert exc_get.value.status_code == 404

    # Update: 200 e 404
    service.update_experience = AsyncMock(return_value={"id": exp_id})
    res_up = await update_experience(
        experience_id=exp_id,
        body=ExperienceUpdateRequest(),
        current_user=mock_user,
        service=service,
    )
    assert res_up == {"id": exp_id}

    service.update_experience = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_up:
        await update_experience(
            experience_id=exp_id,
            body=ExperienceUpdateRequest(),
            current_user=mock_user,
            service=service,
        )
    assert exc_up.value.status_code == 404

    # Delete: 200 e 404
    service.delete_experience = AsyncMock(return_value=True)
    await delete_experience(experience_id=exp_id, current_user=mock_user, service=service)

    service.delete_experience = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc_del:
        await delete_experience(experience_id=exp_id, current_user=mock_user, service=service)
    assert exc_del.value.status_code == 404


@pytest.mark.asyncio
async def test_education_endpoints_direct(mock_user: User) -> None:
    """Valida branches de sucesso e 404 para formações acadêmicas."""
    service = MagicMock()
    edu_id = uuid.uuid4()

    service.create_education = AsyncMock(return_value={"id": edu_id})
    service.list_educations = AsyncMock(return_value=[{"id": edu_id}])
    await create_education(
        body=EducationCreateRequest(
            institution_name="USP",
            degree="Bacharelado",
            field_of_study="Engenharia",
            start_date="2015-01-01",
        ),
        current_user=mock_user,
        service=service,
    )

    await list_educations(current_user=mock_user, service=service)

    # Update: 200 e 404
    service.update_education = AsyncMock(return_value={"id": edu_id})
    res_up = await update_education(
        education_id=edu_id,
        body=EducationUpdateRequest(),
        current_user=mock_user,
        service=service,
    )
    assert res_up == {"id": edu_id}

    service.update_education = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_up:
        await update_education(
            education_id=edu_id,
            body=EducationUpdateRequest(),
            current_user=mock_user,
            service=service,
        )
    assert exc_up.value.status_code == 404

    # Delete: 200 e 404
    service.delete_education = AsyncMock(return_value=True)
    await delete_education(education_id=edu_id, current_user=mock_user, service=service)

    service.delete_education = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc_del:
        await delete_education(education_id=edu_id, current_user=mock_user, service=service)
    assert exc_del.value.status_code == 404


@pytest.mark.asyncio
async def test_certification_endpoints_direct(mock_user: User) -> None:
    """Valida branches de sucesso e 404 para certificações."""
    service = MagicMock()
    cert_id = uuid.uuid4()

    service.create_certification = AsyncMock(return_value={"id": cert_id})
    service.list_certifications = AsyncMock(return_value=[{"id": cert_id}])
    await create_certification(
        body=CertificationCreateRequest(
            name="AWS", issuing_organization="Amazon", issue_date="2023-01-01"
        ),
        current_user=mock_user,
        service=service,
    )
    await list_certifications(current_user=mock_user, service=service)

    # Update: 200 e 404
    service.update_certification = AsyncMock(return_value={"id": cert_id})
    res_up = await update_certification(
        certification_id=cert_id,
        body=CertificationUpdateRequest(),
        current_user=mock_user,
        service=service,
    )
    assert res_up == {"id": cert_id}

    service.update_certification = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_up:
        await update_certification(
            certification_id=cert_id,
            body=CertificationUpdateRequest(),
            current_user=mock_user,
            service=service,
        )
    assert exc_up.value.status_code == 404

    # Delete: 200 e 404
    service.delete_certification = AsyncMock(return_value=True)
    await delete_certification(certification_id=cert_id, current_user=mock_user, service=service)

    service.delete_certification = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc_del:
        await delete_certification(
            certification_id=cert_id, current_user=mock_user, service=service
        )
    assert exc_del.value.status_code == 404


@pytest.mark.asyncio
async def test_project_endpoints_direct(mock_user: User) -> None:
    """Valida branches de sucesso e 404 para projetos."""
    service = MagicMock()
    proj_id = uuid.uuid4()

    service.create_project = AsyncMock(return_value={"id": proj_id})
    service.list_projects = AsyncMock(return_value=[{"id": proj_id}])
    await create_project(
        body=ProjectCreateRequest(title="Proj", description="desc"),
        current_user=mock_user,
        service=service,
    )

    await list_projects(current_user=mock_user, service=service)

    # Update: 200 e 404
    service.update_project = AsyncMock(return_value={"id": proj_id})
    res_up = await update_project(
        project_id=proj_id,
        body=ProjectUpdateRequest(),
        current_user=mock_user,
        service=service,
    )
    assert res_up == {"id": proj_id}

    service.update_project = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_up:
        await update_project(
            project_id=proj_id,
            body=ProjectUpdateRequest(),
            current_user=mock_user,
            service=service,
        )
    assert exc_up.value.status_code == 404

    # Delete: 200 e 404
    service.delete_project = AsyncMock(return_value=True)
    await delete_project(project_id=proj_id, current_user=mock_user, service=service)

    service.delete_project = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc_del:
        await delete_project(project_id=proj_id, current_user=mock_user, service=service)
    assert exc_del.value.status_code == 404


@pytest.mark.asyncio
async def test_skill_endpoints_direct(mock_user: User) -> None:
    """Valida branches de sucesso e 404 para competências."""
    service = MagicMock()
    skill_id = uuid.uuid4()

    service.create_skill = AsyncMock(return_value={"id": skill_id})
    service.list_skills = AsyncMock(return_value=[{"id": skill_id}])
    await create_skill(
        body=SkillCreateRequest(name="Python", category="backend", proficiency_level="expert"),
        current_user=mock_user,
        service=service,
    )
    await list_skills(category="backend", current_user=mock_user, service=service)

    # Update: 200 e 404
    service.update_skill = AsyncMock(return_value={"id": skill_id})
    res_up = await update_skill(
        skill_id=skill_id,
        body=SkillUpdateRequest(),
        current_user=mock_user,
        service=service,
    )
    assert res_up == {"id": skill_id}

    service.update_skill = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_up:
        await update_skill(
            skill_id=skill_id,
            body=SkillUpdateRequest(),
            current_user=mock_user,
            service=service,
        )
    assert exc_up.value.status_code == 404

    # Delete: 200 e 404
    service.delete_skill = AsyncMock(return_value=True)
    await delete_skill(skill_id=skill_id, current_user=mock_user, service=service)

    service.delete_skill = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc_del:
        await delete_skill(skill_id=skill_id, current_user=mock_user, service=service)
    assert exc_del.value.status_code == 404


@pytest.mark.asyncio
async def test_language_endpoints_direct(mock_user: User) -> None:
    """Valida branches de sucesso e 404 para idiomas e dossiê full."""
    service = MagicMock()
    lang_id = uuid.uuid4()

    service.create_language = AsyncMock(return_value={"id": lang_id})
    service.list_languages = AsyncMock(return_value=[{"id": lang_id}])
    await create_language(
        body=LanguageCreateRequest(language_name="Inglês", proficiency_level="fluent"),
        current_user=mock_user,
        service=service,
    )
    await list_languages(current_user=mock_user, service=service)

    # Update: 200 e 404
    service.update_language = AsyncMock(return_value={"id": lang_id})
    res_up = await update_language(
        language_id=lang_id,
        body=LanguageUpdateRequest(),
        current_user=mock_user,
        service=service,
    )
    assert res_up == {"id": lang_id}

    service.update_language = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_up:
        await update_language(
            language_id=lang_id,
            body=LanguageUpdateRequest(),
            current_user=mock_user,
            service=service,
        )
    assert exc_up.value.status_code == 404

    # Delete: 200 e 404
    service.delete_language = AsyncMock(return_value=True)
    await delete_language(language_id=lang_id, current_user=mock_user, service=service)

    service.delete_language = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc_del:
        await delete_language(language_id=lang_id, current_user=mock_user, service=service)
    assert exc_del.value.status_code == 404

    # Full Dossier
    service.get_full_dossier = AsyncMock(return_value={})
    res_dossier = await get_full_dossier(current_user=mock_user, service=service)
    assert res_dossier == {}
