"""Serviço de gerenciamento do Repositório Profissional (Dossiê).

Implementa regras de negócio, isolamento estrito de tenant (multi-tenancy),
ordenação manual e exclusão lógica (soft delete) para todas as entidades do dossiê.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models import (
    Certification,
    Education,
    Experience,
    Language,
    Project,
    Skill,
    User,
)
from app.ports.resume_parser_port import ParsedProfileDTO

logger = get_logger(__name__)


def parse_flexible_date(date_str: str | None, default_day: int = 1) -> date | None:
    """Converte strings de datas variadas (YYYY, YYYY-MM, YYYY-MM-DD) para date.

    Args:
        date_str: String de data a converter.
        default_day: Dia padrão a utilizar quando omitido.

    Returns:
        date | None: Instância de date correspondente ou None se inválida.
    """
    if not date_str:
        return None
    clean = date_str.strip()
    if not clean:
        return None
    parts = clean.split("-")
    try:
        if len(parts) == 1 and len(parts[0]) == 4:
            return date(int(parts[0]), 1, default_day)
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), default_day)
        if len(parts) >= 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2][:2]))
    except Exception:
        return None
    return None


class ProfileService:
    """Encapsula operações transacionais do repositório profissional do candidato.

    Attributes:
        _db: Sessão ativa assíncrona do SQLAlchemy.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o serviço injetando a sessão de banco de dados.

        Args:
            db: Sessão assíncrona do SQLAlchemy.
        """
        self._db = db

    # ==================== EXPERIÊNCIAS ====================
    async def create_experience(self, user_id: uuid.UUID, data: dict[str, Any]) -> Experience:
        """Cadastra uma nova experiência profissional garantindo vínculo ao tenant.

        Args:
            user_id: UUID do usuário proprietário.
            data: Dicionário contendo os dados validados da experiência.

        Returns:
            Experience: Instância persistida da experiência profissional.
        """
        experience = Experience(user_id=user_id, **data)
        self._db.add(experience)
        await self._db.flush()
        return experience

    async def list_experiences(self, user_id: uuid.UUID) -> list[Experience]:
        """Lista todas as experiências ativas do usuário ordenadas por sort_order.

        Args:
            user_id: UUID do usuário autenticado.

        Returns:
            list[Experience]: Experiências profissionais ordenadas.
        """
        result = await self._db.execute(
            select(Experience)
            .where(Experience.user_id == user_id, Experience.deleted_at.is_(None))
            .order_by(Experience.sort_order.asc(), Experience.start_date.desc())
        )
        return list(result.scalars().all())

    async def get_experience(
        self, user_id: uuid.UUID, experience_id: uuid.UUID
    ) -> Experience | None:
        """Recupera uma experiência específica garantindo isolamento por tenant.

        Args:
            user_id: UUID do usuário autenticado.
            experience_id: UUID do registro desejado.

        Returns:
            Experience | None: Entidade encontrada ou None se não existir ou for de outro usuário.
        """
        result = await self._db.execute(
            select(Experience).where(
                Experience.id == experience_id,
                Experience.user_id == user_id,
                Experience.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_experience(
        self, user_id: uuid.UUID, experience_id: uuid.UUID, data: dict[str, Any]
    ) -> Experience | None:
        """Atualiza campos de uma experiência existente.

        Args:
            user_id: UUID do usuário autenticado.
            experience_id: UUID da experiência a atualizar.
            data: Dicionário com campos alterados.

        Returns:
            Experience | None: Entidade atualizada ou None caso não encontrada.
        """
        experience = await self.get_experience(user_id, experience_id)
        if not experience:
            return None

        for key, value in data.items():
            if value is not None:
                setattr(experience, key, value)

        await self._db.flush()
        return experience

    async def delete_experience(self, user_id: uuid.UUID, experience_id: uuid.UUID) -> bool:
        """Realiza exclusão lógica (soft delete) da experiência.

        Args:
            user_id: UUID do usuário autenticado.
            experience_id: UUID da experiência a ser excluída.

        Returns:
            bool: True se o registro foi desativado, False se não encontrado.
        """
        experience = await self.get_experience(user_id, experience_id)
        if not experience:
            return False

        experience.deleted_at = datetime.now(UTC)
        await self._db.flush()
        return True

    # ==================== FORMAÇÃO ACADÊMICA ====================
    async def create_education(self, user_id: uuid.UUID, data: dict[str, Any]) -> Education:
        """Cadastra uma nova formação acadêmica vinculada ao usuário."""
        education = Education(user_id=user_id, **data)
        self._db.add(education)
        await self._db.flush()
        return education

    async def list_educations(self, user_id: uuid.UUID) -> list[Education]:
        """Lista formações acadêmicas ativas ordenadas por sort_order."""
        result = await self._db.execute(
            select(Education)
            .where(Education.user_id == user_id, Education.deleted_at.is_(None))
            .order_by(Education.sort_order.asc(), Education.start_date.desc())
        )
        return list(result.scalars().all())

    async def get_education(self, user_id: uuid.UUID, education_id: uuid.UUID) -> Education | None:
        """Recupera formação acadêmica por ID respeitando isolamento de tenant."""
        result = await self._db.execute(
            select(Education).where(
                Education.id == education_id,
                Education.user_id == user_id,
                Education.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_education(
        self, user_id: uuid.UUID, education_id: uuid.UUID, data: dict[str, Any]
    ) -> Education | None:
        """Atualiza campos de formação acadêmica."""
        education = await self.get_education(user_id, education_id)
        if not education:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(education, key, value)
        await self._db.flush()
        return education

    async def delete_education(self, user_id: uuid.UUID, education_id: uuid.UUID) -> bool:
        """Aplica soft delete na formação acadêmica."""
        education = await self.get_education(user_id, education_id)
        if not education:
            return False
        education.deleted_at = datetime.now(UTC)
        await self._db.flush()
        return True

    # ==================== CERTIFICAÇÕES ====================
    async def create_certification(self, user_id: uuid.UUID, data: dict[str, Any]) -> Certification:
        """Cadastra uma nova certificação técnica."""
        certification = Certification(user_id=user_id, **data)
        self._db.add(certification)
        await self._db.flush()
        return certification

    async def list_certifications(self, user_id: uuid.UUID) -> list[Certification]:
        """Lista certificações ativas do usuário."""
        result = await self._db.execute(
            select(Certification)
            .where(Certification.user_id == user_id, Certification.deleted_at.is_(None))
            .order_by(Certification.sort_order.asc(), Certification.issue_date.desc())
        )
        return list(result.scalars().all())

    async def get_certification(
        self, user_id: uuid.UUID, certification_id: uuid.UUID
    ) -> Certification | None:
        """Recupera certificação por ID do tenant."""
        result = await self._db.execute(
            select(Certification).where(
                Certification.id == certification_id,
                Certification.user_id == user_id,
                Certification.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_certification(
        self, user_id: uuid.UUID, certification_id: uuid.UUID, data: dict[str, Any]
    ) -> Certification | None:
        """Atualiza certificação técnica existente."""
        certification = await self.get_certification(user_id, certification_id)
        if not certification:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(certification, key, value)
        await self._db.flush()
        return certification

    async def delete_certification(self, user_id: uuid.UUID, certification_id: uuid.UUID) -> bool:
        """Aplica soft delete na certificação."""
        certification = await self.get_certification(user_id, certification_id)
        if not certification:
            return False
        certification.deleted_at = datetime.now(UTC)
        await self._db.flush()
        return True

    # ==================== PROJETOS ====================
    async def create_project(self, user_id: uuid.UUID, data: dict[str, Any]) -> Project:
        """Cadastra um novo projeto ou portfólio."""
        project = Project(user_id=user_id, **data)
        self._db.add(project)
        await self._db.flush()
        return project

    async def list_projects(self, user_id: uuid.UUID) -> list[Project]:
        """Lista projetos ativos do usuário."""
        result = await self._db.execute(
            select(Project)
            .where(Project.user_id == user_id, Project.deleted_at.is_(None))
            .order_by(Project.sort_order.asc(), Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> Project | None:
        """Recupera projeto por ID do tenant."""
        result = await self._db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id,
                Project.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_project(
        self, user_id: uuid.UUID, project_id: uuid.UUID, data: dict[str, Any]
    ) -> Project | None:
        """Atualiza projeto existente."""
        project = await self.get_project(user_id, project_id)
        if not project:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(project, key, value)
        await self._db.flush()
        return project

    async def delete_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> bool:
        """Aplica soft delete no projeto."""
        project = await self.get_project(user_id, project_id)
        if not project:
            return False
        project.deleted_at = datetime.now(UTC)
        await self._db.flush()
        return True

    # ==================== COMPETÊNCIAS (SKILLS) ====================
    async def create_skill(self, user_id: uuid.UUID, data: dict[str, Any]) -> Skill:
        """Cadastra uma nova competência técnica ou comportamental."""
        skill = Skill(user_id=user_id, **data)
        self._db.add(skill)
        await self._db.flush()
        return skill

    async def list_skills(self, user_id: uuid.UUID, category: str | None = None) -> list[Skill]:
        """Lista competências do usuário com filtro opcional por categoria."""
        query = select(Skill).where(Skill.user_id == user_id)
        if category:
            query = query.where(Skill.category == category)
        query = query.order_by(Skill.is_featured.desc(), Skill.name.asc())
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def get_skill(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> Skill | None:
        """Recupera competência por ID do tenant."""
        result = await self._db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_skill(
        self, user_id: uuid.UUID, skill_id: uuid.UUID, data: dict[str, Any]
    ) -> Skill | None:
        """Atualiza competência existente."""
        skill = await self.get_skill(user_id, skill_id)
        if not skill:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(skill, key, value)
        await self._db.flush()
        return skill

    async def delete_skill(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> bool:
        """Remove competência do usuário."""
        skill = await self.get_skill(user_id, skill_id)
        if not skill:
            return False
        await self._db.delete(skill)
        await self._db.flush()
        return True

    # ==================== IDIOMAS ====================
    async def create_language(self, user_id: uuid.UUID, data: dict[str, Any]) -> Language:
        """Cadastra idioma dominado pelo usuário."""
        language = Language(user_id=user_id, **data)
        self._db.add(language)
        await self._db.flush()
        return language

    async def list_languages(self, user_id: uuid.UUID) -> list[Language]:
        """Lista todos os idiomas dominados pelo usuário."""
        result = await self._db.execute(
            select(Language)
            .where(Language.user_id == user_id)
            .order_by(Language.language_name.asc())
        )
        return list(result.scalars().all())

    async def get_language(self, user_id: uuid.UUID, language_id: uuid.UUID) -> Language | None:
        """Recupera idioma por ID do tenant."""
        result = await self._db.execute(
            select(Language).where(Language.id == language_id, Language.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_language(
        self, user_id: uuid.UUID, language_id: uuid.UUID, data: dict[str, Any]
    ) -> Language | None:
        """Atualiza fluência de idioma."""
        language = await self.get_language(user_id, language_id)
        if not language:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(language, key, value)
        await self._db.flush()
        return language

    async def delete_language(self, user_id: uuid.UUID, language_id: uuid.UUID) -> bool:
        """Remove idioma do usuário."""
        language = await self.get_language(user_id, language_id)
        if not language:
            return False
        await self._db.delete(language)
        await self._db.flush()
        return True

    # ==================== DOSSIÊ COMPLETO ====================
    async def get_full_dossier(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Recupera de forma agregada todo o dossiê profissional do candidato.

        Args:
            user_id: UUID do usuário autenticado.

        Returns:
            dict[str, Any]: Dicionário agregado pronto para renderização ou matching com IA.
        """
        experiences = await self.list_experiences(user_id)
        educations = await self.list_educations(user_id)
        certifications = await self.list_certifications(user_id)
        projects = await self.list_projects(user_id)
        skills = await self.list_skills(user_id)
        languages = await self.list_languages(user_id)

        return {
            "experiences": experiences,
            "educations": educations,
            "certifications": certifications,
            "projects": projects,
            "skills": skills,
            "languages": languages,
        }

    # ==================== IMPORTAÇÃO DE CURRÍCULO ====================
    async def import_parsed_profile(
        self, user_id: uuid.UUID, parsed_profile: ParsedProfileDTO
    ) -> dict[str, int]:
        """Persiste em lote os dados factuais extraídos pela IA no dossiê do usuário.

        Atualiza os dados de contato do usuário caso ainda não estejam preenchidos
        e insere experiências, formações, competências, certificações, idiomas e projetos.

        Args:
            user_id: UUID do usuário autenticado.
            parsed_profile: DTO contendo as entidades extraídas fielmente do documento.

        Returns:
            dict[str, int]: Contagem de registros adicionados por categoria.
        """
        user = await self._db.get(User, user_id)
        if user and parsed_profile.personal_data:
            pdata = parsed_profile.personal_data
            if pdata.full_name and not user.full_name:
                user.full_name = pdata.full_name.strip()
            if pdata.phone and not user.phone:
                user.phone = pdata.phone.strip()
            if pdata.headline and not user.target_title:
                user.target_title = pdata.headline.strip()
            if pdata.location and not user.location:
                user.location = pdata.location.strip()
            if pdata.linkedin_url and not user.linkedin_url:
                user.linkedin_url = pdata.linkedin_url.strip()
            if pdata.github_url and not user.github_url:
                user.github_url = pdata.github_url.strip()
            if pdata.portfolio_url and not user.portfolio_url:
                user.portfolio_url = pdata.portfolio_url.strip()

        # Experiências
        exp_count = 0
        for exp in parsed_profile.experiences:
            s_date = parse_flexible_date(exp.start_date) or date.today()
            e_date = parse_flexible_date(exp.end_date) if exp.end_date else None
            await self.create_experience(
                user_id=user_id,
                data={
                    "company_name": exp.company_name.strip(),
                    "position_title": exp.position_title.strip(),
                    "location": exp.location.strip() if exp.location else None,
                    "work_model": exp.work_model
                    if exp.work_model in ("remote", "hybrid", "on-site")
                    else "remote",
                    "start_date": s_date,
                    "end_date": e_date,
                    "is_current": exp.is_current,
                    "description": exp.description.strip(),
                    "bullet_points": exp.bullet_points,
                    "tech_stack": exp.tech_stack,
                    "quantifiable_results": exp.quantifiable_results,
                    "sort_order": exp_count,
                },
            )
            exp_count += 1

        # Formações Acadêmicas
        edu_count = 0
        for edu in parsed_profile.educations:
            s_date = parse_flexible_date(edu.start_date) or date.today()
            e_date = parse_flexible_date(edu.end_date) if edu.end_date else None
            await self.create_education(
                user_id=user_id,
                data={
                    "institution_name": edu.institution_name.strip(),
                    "degree": edu.degree.strip(),
                    "field_of_study": edu.field_of_study.strip(),
                    "start_date": s_date,
                    "end_date": e_date,
                    "is_current": edu.is_current,
                    "description": edu.description.strip() if edu.description else None,
                    "sort_order": edu_count,
                },
            )
            edu_count += 1

        # Competências (Skills)
        skill_count = 0
        for sk in parsed_profile.skills:
            await self.create_skill(
                user_id=user_id,
                data={
                    "name": sk.name.strip(),
                    "category": sk.category.strip() if sk.category else "backend",
                    "proficiency_level": (
                        sk.proficiency_level
                        if sk.proficiency_level
                        in (
                            "beginner",
                            "intermediate",
                            "advanced",
                            "expert",
                        )
                        else "intermediate"
                    ),
                    "years_of_experience": max(0, sk.years_of_experience),
                    "is_featured": False,
                },
            )
            skill_count += 1

        # Idiomas
        lang_count = 0
        for lg in parsed_profile.languages:
            await self.create_language(
                user_id=user_id,
                data={
                    "language_name": lg.language_name.strip(),
                    "proficiency_level": lg.proficiency_level.strip()
                    if lg.proficiency_level
                    else "intermediate",
                },
            )
            lang_count += 1

        # Certificações
        cert_count = 0
        for cert in parsed_profile.certifications:
            i_date = parse_flexible_date(cert.issue_date) or date.today()
            exp_date = parse_flexible_date(cert.expiration_date) if cert.expiration_date else None
            await self.create_certification(
                user_id=user_id,
                data={
                    "name": cert.name.strip(),
                    "issuing_organization": cert.issuing_organization.strip(),
                    "issue_date": i_date,
                    "expiration_date": exp_date,
                    "credential_id": cert.credential_id.strip() if cert.credential_id else None,
                    "credential_url": cert.credential_url.strip() if cert.credential_url else None,
                    "sort_order": cert_count,
                },
            )
            cert_count += 1

        # Projetos
        proj_count = 0
        for proj in parsed_profile.projects:
            await self.create_project(
                user_id=user_id,
                data={
                    "title": proj.title.strip(),
                    "description": proj.description.strip(),
                    "role": proj.role.strip() if proj.role else None,
                    "technologies": proj.technologies,
                    "repository_url": proj.repository_url.strip() if proj.repository_url else None,
                    "live_url": proj.live_url.strip() if proj.live_url else None,
                    "sort_order": proj_count,
                },
            )
            proj_count += 1

        await self._db.flush()

        logger.info(
            "profile_batch_import_completed",
            user_id=str(user_id),
            experiences=exp_count,
            educations=edu_count,
            skills=skill_count,
            languages=lang_count,
            certifications=cert_count,
            projects=proj_count,
        )

        return {
            "experiences": exp_count,
            "educations": edu_count,
            "skills": skill_count,
            "languages": lang_count,
            "certifications": cert_count,
            "projects": proj_count,
        }
