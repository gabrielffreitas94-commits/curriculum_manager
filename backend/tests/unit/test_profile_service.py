"""Testes unitários completos para o ProfileService (Repositório Profissional do Candidato).

Valida isolamento estrito por tenant, ordenação, soft deletes e retornos para os 6 domínios
do dossiê: Experiences, Educations, Certifications, Projects, Skills e Languages.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import User
from app.services.profile_service import ProfileService


@pytest.fixture
def profile_user() -> User:
    """Fixture com usuário dono do dossiê."""
    return User(
        id=uuid.uuid4(),
        firebase_uid="profile_service_user_uid",
        email="profile_service@thothcvs.ai",
        full_name="Profile Tester",
    )


@pytest.mark.asyncio
async def test_experiences_service_crud_and_not_found(
    db_session: AsyncSession,
    profile_user: User,
) -> None:
    """Valida CRUD de experiências e retorno None/False para registros inexistentes."""
    db_session.add(profile_user)
    await db_session.flush()

    service = ProfileService(db=db_session)
    user_id = profile_user.id

    # 1. Create
    exp = await service.create_experience(
        user_id=user_id,
        data={
            "company_name": "MegaCorp",
            "position_title": "Software Engineer",
            "start_date": date(2021, 1, 1),
            "is_current": True,
            "description": "APIs escaláveis",
            "tech_stack": ["Python", "FastAPI"],
        },
    )
    assert exp.id is not None
    assert exp.company_name == "MegaCorp"

    # 2. List
    exps = await service.list_experiences(user_id=user_id)
    assert len(exps) == 1

    # 3. Get
    fetched = await service.get_experience(user_id=user_id, experience_id=exp.id)
    assert fetched is not None
    assert fetched.company_name == "MegaCorp"

    # 4. Update
    updated = await service.update_experience(
        user_id=user_id, experience_id=exp.id, data={"position_title": "Senior Engineer"}
    )
    assert updated is not None
    assert updated.position_title == "Senior Engineer"

    # 5. Soft Delete
    deleted_ok = await service.delete_experience(user_id=user_id, experience_id=exp.id)
    assert deleted_ok is True
    assert len(await service.list_experiences(user_id=user_id)) == 0

    # 6. Casos Não Encontrados (None / False)
    random_id = uuid.uuid4()
    assert await service.get_experience(user_id=user_id, experience_id=random_id) is None
    assert (
        await service.update_experience(user_id=user_id, experience_id=random_id, data={}) is None
    )
    assert await service.delete_experience(user_id=user_id, experience_id=random_id) is False


@pytest.mark.asyncio
async def test_educations_certifications_and_projects_service(
    db_session: AsyncSession,
    profile_user: User,
) -> None:
    """Valida CRUD e casos de borda para Formações, Certificações e Projetos."""
    db_session.add(profile_user)
    await db_session.flush()

    service = ProfileService(db=db_session)
    user_id = profile_user.id
    fake_id = uuid.uuid4()

    # --- Educations ---
    edu = await service.create_education(
        user_id=user_id,
        data={
            "institution_name": "USP",
            "degree": "Bacharelado",
            "field_of_study": "CC",
            "start_date": date(2016, 1, 1),
        },
    )
    assert edu.id is not None
    assert len(await service.list_educations(user_id=user_id)) == 1
    assert await service.get_education(user_id=user_id, education_id=edu.id) is not None
    assert (
        await service.update_education(
            user_id=user_id, education_id=edu.id, data={"degree": "Mestrado"}
        )
    ).degree == "Mestrado"
    assert await service.delete_education(user_id=user_id, education_id=edu.id) is True
    assert await service.get_education(user_id=user_id, education_id=fake_id) is None
    assert await service.update_education(user_id=user_id, education_id=fake_id, data={}) is None
    assert await service.delete_education(user_id=user_id, education_id=fake_id) is False

    # --- Certifications ---
    cert = await service.create_certification(
        user_id=user_id,
        data={
            "name": "GCP Architect",
            "issuing_organization": "Google",
            "issue_date": date(2022, 5, 10),
        },
    )
    assert cert.id is not None
    assert len(await service.list_certifications(user_id=user_id)) == 1
    assert await service.get_certification(user_id=user_id, certification_id=cert.id) is not None
    assert (
        await service.update_certification(
            user_id=user_id, certification_id=cert.id, data={"name": "GCP Cloud Leader"}
        )
    ).name == "GCP Cloud Leader"
    assert await service.delete_certification(user_id=user_id, certification_id=cert.id) is True
    assert await service.get_certification(user_id=user_id, certification_id=fake_id) is None
    assert (
        await service.update_certification(user_id=user_id, certification_id=fake_id, data={})
        is None
    )
    assert await service.delete_certification(user_id=user_id, certification_id=fake_id) is False

    # --- Projects ---
    proj = await service.create_project(
        user_id=user_id,
        data={"title": "Open Source ATS", "description": "Projeto"},
    )
    assert proj.id is not None
    assert len(await service.list_projects(user_id=user_id)) == 1
    assert await service.get_project(user_id=user_id, project_id=proj.id) is not None
    assert (
        await service.update_project(
            user_id=user_id, project_id=proj.id, data={"title": "Open ATS Pro"}
        )
    ).title == "Open ATS Pro"
    assert await service.delete_project(user_id=user_id, project_id=proj.id) is True
    assert await service.get_project(user_id=user_id, project_id=fake_id) is None
    assert await service.update_project(user_id=user_id, project_id=fake_id, data={}) is None
    assert await service.delete_project(user_id=user_id, project_id=fake_id) is False


@pytest.mark.asyncio
async def test_skills_and_languages_service(
    db_session: AsyncSession,
    profile_user: User,
) -> None:
    """Valida competências com filtro de categoria e idiomas."""
    db_session.add(profile_user)
    await db_session.flush()

    service = ProfileService(db=db_session)
    user_id = profile_user.id
    fake_id = uuid.uuid4()

    # --- Skills ---
    s1 = await service.create_skill(
        user_id=user_id,
        data={"name": "FastAPI", "category": "backend", "proficiency_level": "expert"},
    )
    s2 = await service.create_skill(
        user_id=user_id,
        data={"name": "React", "category": "frontend", "proficiency_level": "intermediate"},
    )
    assert s2.id is not None
    assert len(await service.list_skills(user_id=user_id)) == 2
    assert len(await service.list_skills(user_id=user_id, category="backend")) == 1
    assert len(await service.list_skills(user_id=user_id, category="devops")) == 0

    assert await service.get_skill(user_id=user_id, skill_id=s1.id) is not None
    assert (
        await service.update_skill(
            user_id=user_id, skill_id=s1.id, data={"proficiency_level": "advanced"}
        )
    ).proficiency_level == "advanced"
    assert await service.delete_skill(user_id=user_id, skill_id=s1.id) is True
    assert await service.get_skill(user_id=user_id, skill_id=fake_id) is None
    assert await service.update_skill(user_id=user_id, skill_id=fake_id, data={}) is None
    assert await service.delete_skill(user_id=user_id, skill_id=fake_id) is False

    # --- Languages ---
    lang = await service.create_language(
        user_id=user_id,
        data={"language_name": "Inglês", "proficiency_level": "fluent"},
    )
    assert lang.id is not None
    assert len(await service.list_languages(user_id=user_id)) == 1
    assert await service.get_language(user_id=user_id, language_id=lang.id) is not None
    assert (
        await service.update_language(
            user_id=user_id, language_id=lang.id, data={"proficiency_level": "native"}
        )
    ).proficiency_level == "native"
    assert await service.delete_language(user_id=user_id, language_id=lang.id) is True
    assert await service.get_language(user_id=user_id, language_id=fake_id) is None
    assert await service.update_language(user_id=user_id, language_id=fake_id, data={}) is None
    assert await service.delete_language(user_id=user_id, language_id=fake_id) is False


@pytest.mark.asyncio
async def test_get_full_dossier(
    db_session: AsyncSession,
    profile_user: User,
) -> None:
    """Valida o método agregador get_full_dossier retornando todas as coleções."""
    db_session.add(profile_user)
    await db_session.flush()

    service = ProfileService(db=db_session)
    user_id = profile_user.id

    await service.create_experience(
        user_id=user_id,
        data={
            "company_name": "Alpha Corp",
            "position_title": "Engineer",
            "start_date": date(2022, 1, 1),
            "description": "Desenvolvimento de software",
        },
    )

    await service.create_skill(
        user_id=user_id,
        data={"name": "Docker", "category": "devops"},
    )

    dossier = await service.get_full_dossier(user_id=user_id)
    assert "experiences" in dossier
    assert "educations" in dossier
    assert "certifications" in dossier
    assert "projects" in dossier
    assert "skills" in dossier
    assert "languages" in dossier
    assert len(dossier["experiences"]) == 1
    assert len(dossier["skills"]) == 1
    assert len(dossier["educations"]) == 0


def test_parse_flexible_date() -> None:
    """Valida a conversão de strings de data nos mais diversos formatos aceitos."""
    from app.services.profile_service import parse_flexible_date

    assert parse_flexible_date(None) is None
    assert parse_flexible_date("") is None
    assert parse_flexible_date("   ") is None
    assert parse_flexible_date("2024") == date(2024, 1, 1)
    assert parse_flexible_date("2024-06") == date(2024, 6, 1)
    assert parse_flexible_date("2024-06-25") == date(2024, 6, 25)
    assert parse_flexible_date("invalid-date-format") is None
    assert parse_flexible_date("99999-99-99") is None


@pytest.mark.asyncio
async def test_import_parsed_profile_full_flow(
    db_session: AsyncSession,
    profile_user: User,
) -> None:
    """Valida persistência em lote do perfil extraído por IA e atualização dos dados do usuário."""
    from app.ports.resume_parser_port import (
        ParsedCertificationDTO,
        ParsedEducationDTO,
        ParsedExperienceDTO,
        ParsedLanguageDTO,
        ParsedPersonalDataDTO,
        ParsedProfileDTO,
        ParsedProjectDTO,
        ParsedSkillDTO,
    )

    db_session.add(profile_user)
    await db_session.flush()

    service = ProfileService(db=db_session)
    user_id = profile_user.id

    parsed_dto = ParsedProfileDTO(
        personal_data=ParsedPersonalDataDTO(
            full_name="Novo Nome Atualizado",
            headline="Tech Lead",
            phone="+55 11 98888-1234",
            location="Curitiba, PR",
            linkedin_url="https://linkedin.com/in/novoperfil",
            github_url="https://github.com/novogithub",
            portfolio_url="https://meusite.com",
        ),
        experiences=[
            ParsedExperienceDTO(
                company_name="Alpha Tech",
                position_title="Software Architect",
                location="Remoto",
                work_model="remote",
                start_date="2021-03",
                end_date=None,
                is_current=True,
                description="Desenvolvimento em larga escala.",
                tech_stack=["Python", "Kafka"],
            )
        ],
        educations=[
            ParsedEducationDTO(
                institution_name="Universidade Federal",
                degree="Mestrado",
                field_of_study="IA",
                start_date="2019",
                end_date="2021",
                is_current=False,
            )
        ],
        skills=[
            ParsedSkillDTO(
                name="Kubernetes",
                category="devops",
                proficiency_level="expert",
                years_of_experience=5,
            )
        ],
        languages=[
            ParsedLanguageDTO(
                language_name="Inglês",
                proficiency_level="fluente",
            )
        ],
        certifications=[
            ParsedCertificationDTO(
                name="AWS Certified Solutions Architect",
                issuing_organization="AWS",
                issue_date="2023-01-15",
            )
        ],
        projects=[
            ParsedProjectDTO(
                title="Curriculum Engine",
                description="Motor de currículos",
                technologies=["FastAPI", "HTMX"],
            )
        ],
    )

    counts = await service.import_parsed_profile(user_id=user_id, parsed_profile=parsed_dto)
    assert counts["experiences"] == 1
    assert counts["educations"] == 1
    assert counts["skills"] == 1
    assert counts["languages"] == 1
    assert counts["certifications"] == 1
    assert counts["projects"] == 1

    # Valida que dados cadastrais foram propagados para a entidade User
    assert profile_user.target_title == "Tech Lead"
    assert profile_user.phone == "+55 11 98888-1234"
    assert profile_user.location == "Curitiba, PR"
    assert profile_user.linkedin_url == "https://linkedin.com/in/novoperfil"
    assert profile_user.github_url == "https://github.com/novogithub"
    assert profile_user.portfolio_url == "https://meusite.com"


@pytest.mark.asyncio
async def test_import_parsed_profile_fills_empty_full_name(
    db_session: AsyncSession,
) -> None:
    """Valida preenchimento de full_name no User quando previamente vazio."""
    from app.ports.resume_parser_port import ParsedPersonalDataDTO, ParsedProfileDTO

    user = User(
        id=uuid.uuid4(),
        firebase_uid="uid_empty_name",
        email="empty_name@thoth.ai",
        full_name="",
    )
    db_session.add(user)
    await db_session.flush()

    service = ProfileService(db=db_session)
    dto = ParsedProfileDTO(
        personal_data=ParsedPersonalDataDTO(full_name="Extracted Name"),
    )
    await service.import_parsed_profile(user_id=user.id, parsed_profile=dto)
    assert user.full_name == "Extracted Name"


def test_parse_flexible_date_edge_cases() -> None:
    """Valida casos extremos de parsing flexível de datas (anos incompletos, inválidos)."""
    from app.services.profile_service import parse_flexible_date

    assert parse_flexible_date("123") is None
    assert parse_flexible_date("2024-invalid") is None
    assert parse_flexible_date("") is None
    assert parse_flexible_date(None) is None
    assert parse_flexible_date("2023") == date(2023, 1, 1)
    assert parse_flexible_date("2023-05") == date(2023, 5, 1)
    assert parse_flexible_date("2023-05-15") == date(2023, 5, 15)
