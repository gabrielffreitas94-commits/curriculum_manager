"""Serviço de orquestração do Copilot Interativo de IA para personalização de currículos.

Gerencia o diálogo consultivo entre o candidato e o motor Gemini, injetando o
Dossiê Mestre (Ground Truth), as diretrizes da metodologia selecionada (PromptSkill)
e garantindo conformidade com a Arquitetura Hexagonal (consumindo AIPort via DI).
"""

import time
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models import User
from app.ports.ai_port import AIError, AIPort, ChatMessage, MissingApiKeyError
from app.services.profile_service import ProfileService
from app.services.prompt_skill_service import PromptSkillService

logger = get_logger(__name__)


class CopilotService:
    """Orquestrador da experiência conversacional com o Copilot de IA.

    Attributes:
        _db: Sessão assíncrona do banco de dados relacional.
        _ai_port: Porta abstrata de integração com LLMs.
    """

    def __init__(self, db: AsyncSession, ai_port: AIPort) -> None:
        """Inicializa o serviço recebendo as portas via Inversão de Dependências."""
        self._db = db
        self._ai_port = ai_port

    async def chat(
        self,
        user: User,
        job_description: str,
        prompt_skill_slug: str,
        messages: list[ChatMessage],
    ) -> str:
        """Executa um turno de conversa com o Copilot Tailoring Assistant.

        Args:
            user: Candidato autenticado.
            job_description: Texto integral da vaga.
            prompt_skill_slug: Slug da metodologia/persona escolhida.
            messages: Histórico da conversa multi-turn.

        Returns:
            str: Resposta consultiva gerada pela IA.

        Raises:
            HTTPException: 400 se parâmetros forem inválidos ou chave ausente;
                           502 se houver falha de upstream com a IA.
        """
        if not job_description or not job_description.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A descrição da vaga de emprego é obrigatória para consultar o Copilot.",
            )

        if not messages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O histórico de mensagens não pode ser vazio.",
            )

        start_time = time.perf_counter()

        # 1. Recupera o Dossiê Factual Real do Candidato (Ground Truth)
        profile_service = ProfileService(self._db)
        raw_dossier = await profile_service.get_full_dossier(user.id)

        user_companies = [e.company_name for e in raw_dossier["experiences"]]
        user_positions = [e.position_title for e in raw_dossier["experiences"]]
        user_skills = [s.name for s in raw_dossier["skills"]]
        for exp in raw_dossier["experiences"]:
            user_skills.extend(exp.tech_stack or [])
        for proj in raw_dossier["projects"]:
            user_skills.extend(proj.technologies or [])

        ground_truth: dict[str, Any] = {
            "full_name": user.full_name,
            "target_title": user.target_title,
            "professional_summary": user.professional_summary,
            "companies": list(set(user_companies)),
            "positions": list(set(user_positions)),
            "skills": list(set(user_skills)),
            "experiences": [
                {
                    "company": exp.company_name,
                    "position": exp.position_title,
                    "achievements": exp.bullet_points or [],
                    "tech_stack": exp.tech_stack or [],
                }
                for exp in raw_dossier["experiences"]
            ],
            "educations": [
                {"institution": ed.institution_name, "degree": ed.degree}
                for ed in raw_dossier["educations"]
            ],
            "certifications": [c.name for c in raw_dossier["certifications"]],
            "projects": [
                {
                    "title": p.title,
                    "description": p.description,
                    "technologies": p.technologies or [],
                }
                for p in raw_dossier["projects"]
            ],
        }

        # 2. Resolução da Metodologia / PromptSkill
        skill_service = PromptSkillService(self._db)
        prompt_skill = await skill_service.get_by_slug(prompt_skill_slug)

        if prompt_skill:
            skill_instructions = prompt_skill.system_prompt
        else:
            skill_instructions = (
                "Estruture bullet points com métricas quantitativas, foco em impacto e clareza."
            )

        # 3. Interação com a Porta de IA
        try:
            copilot_reply = await self._ai_port.chat_tailoring(
                messages=messages,
                job_description=job_description,
                user_dossier=ground_truth,
                prompt_skill_instructions=skill_instructions,
            )
        except MissingApiKeyError as exc:
            logger.warning("copilot_chat_missing_api_key", user_id=str(user.id))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chave de API do Gemini não configurada. Cadastre-a nas configurações.",
            ) from exc
        except AIError as exc:
            logger.error("copilot_chat_upstream_error", user_id=str(user.id), error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Falha na comunicação com o Copilot de IA: {exc}",
            ) from exc

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "copilot_chat_turn_completed",
            user_id=str(user.id),
            prompt_skill_slug=prompt_skill_slug,
            messages_count=len(messages),
            duration_ms=duration_ms,
        )

        return copilot_reply
