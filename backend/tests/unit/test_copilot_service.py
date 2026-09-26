"""Testes unitários para o CopilotService."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    Certification,
    Education,
    Experience,
    Project,
    PromptSkill,
    Skill,
    User,
)
from app.ports.ai_port import AIError, AIPort, ChatMessage, MissingApiKeyError
from app.services.copilot_service import CopilotService


@pytest.mark.asyncio
async def test_copilot_chat_validation_errors(db_session: AsyncSession) -> None:
    """Valida rejeição de inputs vazios (job_description ou messages vazias)."""
    mock_ai = MagicMock(spec=AIPort)
    service = CopilotService(db_session, mock_ai)

    user = User(
        firebase_uid="uid-val-test",
        email="val@example.com",
        full_name="User Val",
    )
    db_session.add(user)
    await db_session.commit()

    # Job description vazio
    with pytest.raises(HTTPException) as exc_info:
        await service.chat(
            user=user,
            job_description="",
            prompt_skill_slug="google-xyz",
            messages=[ChatMessage(role="user", content="Oi")],
        )
    assert exc_info.value.status_code == 400
    assert "descrição da vaga de emprego é obrigatória" in exc_info.value.detail

    # Messages vazias
    with pytest.raises(HTTPException) as exc_info2:
        await service.chat(
            user=user,
            job_description="Vaga Tech Lead",
            prompt_skill_slug="google-xyz",
            messages=[],
        )
    assert exc_info2.value.status_code == 400
    assert "histórico de mensagens não pode ser vazio" in exc_info2.value.detail


@pytest.mark.asyncio
async def test_copilot_chat_success_with_full_grounding(db_session: AsyncSession) -> None:
    """Valida o fluxo de sucesso com resolução completa de dossiê factual e PromptSkill."""
    mock_ai = AsyncMock(spec=AIPort)
    mock_ai.chat_tailoring.return_value = (
        "Recomendo aplicar a Fórmula Google XYZ destacando a redução de latência."
    )
    service = CopilotService(db_session, mock_ai)

    # Cria usuário com perfil detalhado
    user = User(
        firebase_uid="uid-copilot-user",
        email="copilot@example.com",
        full_name="Carlos Alberto",
        target_title="Senior Python Architect",
        professional_summary="Especialista em microsserviços e nuvem.",
    )
    db_session.add(user)
    await db_session.flush()

    from datetime import date

    exp = Experience(
        user_id=user.id,
        company_name="CloudCorp",
        position_title="Senior Backend Engineer",
        description="Atuação em backend",
        start_date=date(2021, 1, 1),
        bullet_points=["Otimizou APIs reduzindo 50% do tempo de resposta"],
        tech_stack=["Python", "FastAPI", "PostgreSQL"],
    )
    edu = Education(
        user_id=user.id,
        institution_name="Universidade Federal",
        degree="Bacharelado",
        field_of_study="Ciência da Computação",
        start_date=date(2016, 2, 1),
    )
    cert = Certification(
        user_id=user.id,
        name="AWS Certified Solutions Architect",
        issuing_organization="Amazon Web Services",
        issue_date=date(2022, 5, 10),
    )
    proj = Project(
        user_id=user.id,
        title="ThothCVs Platform",
        description="Plataforma de IA com arquitetura hexagonal",
        technologies=["Python", "FastAPI", "Docker"],
    )
    skill = Skill(
        user_id=user.id,
        name="Python",
        category="backend",
    )
    prompt_skill = PromptSkill(
        slug="google-xyz",
        name="Fórmula Google XYZ",
        description="Fórmula de impacto",
        category="tech",
        system_prompt="Diretrizes específicas da fórmula Google XYZ.",
        default_language="pt-BR",
        is_system_default=True,
    )
    db_session.add_all([exp, edu, cert, proj, skill, prompt_skill])
    await db_session.commit()

    messages = [
        ChatMessage(role="user", content="Como destacar meu projeto ThothCVs?"),
    ]

    reply = await service.chat(
        user=user,
        job_description="Vaga Tech Lead Python FastAPI",
        prompt_skill_slug="google-xyz",
        messages=messages,
    )

    assert "Fórmula Google XYZ" in reply
    assert mock_ai.chat_tailoring.called

    call_args = mock_ai.chat_tailoring.call_args.kwargs
    assert call_args["job_description"] == "Vaga Tech Lead Python FastAPI"
    assert call_args["prompt_skill_instructions"] == "Diretrizes específicas da fórmula Google XYZ."
    dossier = call_args["user_dossier"]
    assert "CloudCorp" in dossier["companies"]
    assert "Senior Backend Engineer" in dossier["positions"]
    assert "AWS Certified Solutions Architect" in dossier["certifications"]
    assert any(p["title"] == "ThothCVs Platform" for p in dossier["projects"])


@pytest.mark.asyncio
async def test_copilot_chat_fallback_prompt_skill(db_session: AsyncSession) -> None:
    """Valida fallback suave para instruções padrão quando o slug da skill não existe."""
    mock_ai = AsyncMock(spec=AIPort)
    mock_ai.chat_tailoring.return_value = "Sugestão genérica de impacto."
    service = CopilotService(db_session, mock_ai)

    user = User(
        firebase_uid="uid-fallback-user",
        email="fallback@example.com",
        full_name="User Fallback",
    )
    db_session.add(user)
    await db_session.commit()

    reply = await service.chat(
        user=user,
        job_description="Vaga qualquer",
        prompt_skill_slug="unknown-skill-slug",
        messages=[ChatMessage(role="user", content="Ajuda")],
    )

    assert reply == "Sugestão genérica de impacto."
    call_args = mock_ai.chat_tailoring.call_args.kwargs
    assert "Estruture bullet points" in call_args["prompt_skill_instructions"]


@pytest.mark.asyncio
async def test_copilot_chat_missing_api_key_error(db_session: AsyncSession) -> None:
    """Valida conversão de MissingApiKeyError em HTTPException 400."""
    mock_ai = AsyncMock(spec=AIPort)
    mock_ai.chat_tailoring.side_effect = MissingApiKeyError("Chave ausente")
    service = CopilotService(db_session, mock_ai)

    user = User(
        firebase_uid="uid-no-key",
        email="nokey@example.com",
        full_name="User No Key",
    )
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await service.chat(
            user=user,
            job_description="Vaga Tech",
            prompt_skill_slug="google-xyz",
            messages=[ChatMessage(role="user", content="Oi")],
        )
    assert exc_info.value.status_code == 400
    assert "Chave de API do Gemini não configurada" in exc_info.value.detail


@pytest.mark.asyncio
async def test_copilot_chat_upstream_ai_error(db_session: AsyncSession) -> None:
    """Valida conversão de AIError em HTTPException 502 Bad Gateway."""
    mock_ai = AsyncMock(spec=AIPort)
    mock_ai.chat_tailoring.side_effect = AIError("Quota esgotada no Google")
    service = CopilotService(db_session, mock_ai)

    user = User(
        firebase_uid="uid-error-user",
        email="error@example.com",
        full_name="User Error",
    )
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await service.chat(
            user=user,
            job_description="Vaga Tech",
            prompt_skill_slug="google-xyz",
            messages=[ChatMessage(role="user", content="Oi")],
        )
    assert exc_info.value.status_code == 502
    assert "Falha na comunicação com o Copilot de IA" in exc_info.value.detail
