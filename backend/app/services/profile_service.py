"""Serviço de gerenciamento do Repositório Profissional (Dossiê).

Implementa regras de negócio, isolamento estrito de tenant (multi-tenancy),
ordenação manual e exclusão lógica (soft delete) para todas as entidades do dossiê.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    Certification,
    Education,
    Experience,
    Language,
    Project,
    Skill,
)


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
    async def create_experience(
        self, user_id: uuid.UUID, data: dict[str, Any]
    ) -> Experience:
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

    async def delete_experience(
        self, user_id: uuid.UUID, experience_id: uuid.UUID
    ) -> bool:
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
    async def create_education(
        self, user_id: uuid.UUID, data: dict[str, Any]
    ) -> Education:
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

    async def get_education(
        self, user_id: uuid.UUID, education_id: uuid.UUID
    ) -> Education | None:
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

    async def delete_education(
        self, user_id: uuid.UUID, education_id: uuid.UUID
    ) -> bool:
        """Aplica soft delete na formação acadêmica."""
        education = await self.get_education(user_id, education_id)
        if not education:
            return False
        education.deleted_at = datetime.now(UTC)
        await self._db.flush()
        return True

    # ==================== CERTIFICAÇÕES ====================
    async def create_certification(
        self, user_id: uuid.UUID, data: dict[str, Any]
    ) -> Certification:
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

    async def delete_certification(
        self, user_id: uuid.UUID, certification_id: uuid.UUID
    ) -> bool:
        """Aplica soft delete na certificação."""
        certification = await self.get_certification(user_id, certification_id)
        if not certification:
            return False
        certification.deleted_at = datetime.now(UTC)
        await self._db.flush()
        return True

    # ==================== PROJETOS ====================
    async def create_project(
        self, user_id: uuid.UUID, data: dict[str, Any]
    ) -> Project:
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

    async def get_project(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> Project | None:
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

    async def delete_project(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> bool:
        """Aplica soft delete no projeto."""
        project = await self.get_project(user_id, project_id)
        if not project:
            return False
        project.deleted_at = datetime.now(UTC)
        await self._db.flush()
        return True

    # ==================== COMPETÊNCIAS (SKILLS) ====================
    async def create_skill(
        self, user_id: uuid.UUID, data: dict[str, Any]
    ) -> Skill:
        """Cadastra uma nova competência técnica ou comportamental."""
        skill = Skill(user_id=user_id, **data)
        self._db.add(skill)
        await self._db.flush()
        return skill

    async def list_skills(
        self, user_id: uuid.UUID, category: str | None = None
    ) -> list[Skill]:
        """Lista competências do usuário com filtro opcional por categoria."""
        query = select(Skill).where(Skill.user_id == user_id)
        if category:
            query = query.where(Skill.category == category)
        query = query.order_by(Skill.is_featured.desc(), Skill.name.asc())
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def get_skill(
        self, user_id: uuid.UUID, skill_id: uuid.UUID
    ) -> Skill | None:
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

    async def delete_skill(
        self, user_id: uuid.UUID, skill_id: uuid.UUID
    ) -> bool:
        """Remove competência do usuário."""
        skill = await self.get_skill(user_id, skill_id)
        if not skill:
            return False
        await self._db.delete(skill)
        await self._db.flush()
        return True

    # ==================== IDIOMAS ====================
    async def create_language(
        self, user_id: uuid.UUID, data: dict[str, Any]
    ) -> Language:
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

    async def get_language(
        self, user_id: uuid.UUID, language_id: uuid.UUID
    ) -> Language | None:
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

    async def delete_language(
        self, user_id: uuid.UUID, language_id: uuid.UUID
    ) -> bool:
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
