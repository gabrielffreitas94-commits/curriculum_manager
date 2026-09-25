"""Serviço de gerenciamento e catálogo de PromptSkills (Metodologias de Currículo).

Administra as 5 metodologias padrão de mercado (Google XYZ, STAR, Startup, Enterprise,
Executive) e permite a seleção e extensão de personas para o motor de IA.
"""

import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models import PromptSkill

logger = get_logger(__name__)

# Catálogo oficial das 5 metodologias canônicas do ThothCVs AI
SYSTEM_PROMPT_SKILLS: list[dict[str, str | bool]] = [
    {
        "slug": "google-xyz",
        "name": "Fórmula Google XYZ",
        "description": (
            "Estruturação de alto impacto: 'Realizou [X], medido por [Y], fazendo [Z]'. "
            "Recomendado para Big Techs, engenharia de ponta e cargos orientados a métricas."
        ),
        "category": "tech",
        "system_prompt": (
            "Você deve estruturar cada experiência e realização rigorosamente na Fórmula Google "
            "XYZ: 'Realizou [X], medido por [Y], fazendo [Z]'. Enfatize sempre métricas "
            "quantitativas reais (porcentagens, latências, volumes, throughput, tempo economizado) "
            "presentes no dossiê. Priorize verbos de ação assertivos e clareza técnica absoluta."
        ),
        "default_language": "pt-BR",
        "is_system_default": True,
    },
    {
        "slug": "star-method",
        "name": "Método STAR",
        "description": (
            "Storytelling estruturado em Situação, Tarefa, Ação e Resultado. "
            "Ideal para entrevistas comportamentais e descrições ricas em contexto."
        ),
        "category": "general",
        "system_prompt": (
            "Você deve organizar as realizações seguindo o consagrado Método STAR (Situação, "
            "Tarefa, Ação e Resultado). Descreva sucintamente o cenário desafiador (S), o objetivo "
            "a ser alcançado (T), as iniciativas e tecnologias empregadas pelo candidato (A) e o "
            "resultado mensurável e impacto gerado (R)."
        ),
        "default_language": "pt-BR",
        "is_system_default": True,
    },
    {
        "slug": "tech-startup",
        "name": "Startup & High-Growth",
        "description": (
            "Ênfase em velocidade de entrega, autonomia ponta a ponta (ownership), escala e "
            "impacto direto no crescimento do produto."
        ),
        "category": "tech",
        "system_prompt": (
            "Adote uma linguagem dinâmica orientada a Startups e empresas de alto crescimento. "
            "Evidencie senso de dono (ownership), autonomia, velocidade de iteração, resiliência "
            "em cenários incertos, pragmatismo e impacto direto nas métricas de negócio e na "
            "experiência do usuário."
        ),
        "default_language": "pt-BR",
        "is_system_default": True,
    },
    {
        "slug": "enterprise-gov",
        "name": "Enterprise, Governança & Segurança",
        "description": (
            "Foco em conformidade, arquitetura corporativa, alta disponibilidade (99.99%+), "
            "resiliência e gestão de riscos."
        ),
        "category": "corporate",
        "system_prompt": (
            "Enfatize padrões de excelência corporativa (Enterprise), segurança da informação, "
            "conformidade regulatória, alta disponibilidade (99.99%+), arquitetura robusta, "
            "governança de TI, documentação impecável e coordenação eficiente de múltiplos "
            "stakeholders."
        ),
        "default_language": "pt-BR",
        "is_system_default": True,
    },
    {
        "slug": "executive-leadership",
        "name": "Liderança Executiva & Estratégica",
        "description": (
            "Foco em liderança de equipes multidisciplinares, visão de longo prazo, "
            "gestão orçamentária/P&L e transformação de negócios."
        ),
        "category": "executive",
        "system_prompt": (
            "Posicione o perfil com tom executivo e visão estratégica de liderança. Destaque "
            "estruturação e mentoria de equipes de alta performance, gestão orçamentária, "
            "tomada de decisões estratégicas de longo prazo, interlocução com C-level e "
            "transformação digital."
        ),
        "default_language": "pt-BR",
        "is_system_default": True,
    },
]


class PromptSkillService:
    """Serviço de domínio para consulta e semeadura de PromptSkills / Metodologias."""

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o serviço com a sessão do banco relacional."""
        self._db = db

    async def ensure_system_prompt_skills(self) -> list[PromptSkill]:
        """Garante de forma idempotente a existência das 5 metodologias padrão no banco.

        Returns:
            list[PromptSkill]: Lista de entidades das metodologias ativas no sistema.
        """
        start_time = time.perf_counter()
        seeded_count = 0

        # Busca todos os slugs existentes
        stmt = select(PromptSkill)
        result = await self._db.execute(stmt)
        existing_skills = {s.slug: s for s in result.scalars().all()}

        for skill_data in SYSTEM_PROMPT_SKILLS:
            slug = str(skill_data["slug"])
            if slug not in existing_skills:
                new_skill = PromptSkill(
                    slug=slug,
                    name=str(skill_data["name"]),
                    description=str(skill_data["description"]),
                    category=str(skill_data["category"]),
                    system_prompt=str(skill_data["system_prompt"]),
                    default_language=str(skill_data["default_language"]),
                    is_system_default=bool(skill_data["is_system_default"]),
                    created_by_user_id=None,
                    is_active=True,
                )
                self._db.add(new_skill)
                existing_skills[slug] = new_skill
                seeded_count += 1

        if seeded_count > 0:
            await self._db.commit()
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "system_prompt_skills_seeded",
                seeded_count=seeded_count,
                total_skills=len(existing_skills),
                duration_ms=duration_ms,
            )

        return list(existing_skills.values())

    async def list_active_skills(self, user_id: uuid.UUID | None = None) -> list[PromptSkill]:
        """Lista todas as metodologias padrão e as personas personalizadas criadas pelo usuário.

        Args:
            user_id: Identificador opcional do usuário autenticado.

        Returns:
            list[PromptSkill]: Lista ordenada com as metodologias do sistema primeiro.
        """
        # Garante previamente que as skills de sistema existem
        await self.ensure_system_prompt_skills()

        stmt = (
            select(PromptSkill)
            .where(
                PromptSkill.is_active.is_(True),
                (PromptSkill.is_system_default.is_(True))
                | (PromptSkill.created_by_user_id == user_id if user_id else False),
            )
            .order_by(PromptSkill.is_system_default.desc(), PromptSkill.name.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_slug(self, slug: str) -> PromptSkill | None:
        """Localiza uma metodologia pelo seu slug único.

        Args:
            slug: Identificador amigável da skill.

        Returns:
            PromptSkill ou None se inexistente.
        """
        stmt = select(PromptSkill).where(PromptSkill.slug == slug, PromptSkill.is_active.is_(True))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
