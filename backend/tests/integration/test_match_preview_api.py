"""Testes de integração para o endpoint de pré-visualização de aderência (/match-preview).

Permite ao candidato calcular rapidamente o fit cultural/técnico contra o anúncio
da vaga antes de optar pela síntese do currículo.
"""

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import crypto_service
from app.domain.models import Skill, User, UserSettings
from app.ports.ai_port import JobAnalysisResult
from app.ports.auth_port import AuthUser

USER_MATCH_ID = uuid.uuid4()

AUTH_USER = AuthUser(
    uid="user_match_test",
    email="match_test@example.com",
    full_name="Match Tester",
)


@pytest.fixture
async def setup_match_user(db_session: AsyncSession) -> dict:
    """Configura usuário, chave de API e competências para teste de match preview."""
    user = User(
        id=USER_MATCH_ID,
        firebase_uid="user_match_test",
        email="match_test@example.com",
        full_name="Match Tester",
    )
    db_session.add(user)
    await db_session.flush()

    settings = UserSettings(
        user_id=user.id,
        encrypted_gemini_api_key=crypto_service.encrypt("AIzaSyMockKeyForMatchTesting"),
    )
    db_session.add(settings)

    s1 = Skill(id=uuid.uuid4(), user_id=user.id, name="Python", category="Backend")
    s2 = Skill(id=uuid.uuid4(), user_id=user.id, name="FastAPI", category="Backend")
    db_session.add_all([s1, s2])
    await db_session.commit()

    return {
        "headers": {"Authorization": "Bearer token_match"},
    }


@pytest.mark.asyncio
async def test_match_preview_endpoint(
    async_client: AsyncClient,
    setup_match_user: dict,
) -> None:
    """Valida o cálculo do score de match sem disparar a síntese completa do documento."""
    headers = setup_match_user["headers"]

    mock_analysis = JobAnalysisResult(
        job_title="Python Developer",
        seniority_level="Pleno",
        mandatory_requirements=["Python"],
        desirable_requirements=["Docker"],
        keywords=["Python", "FastAPI", "Docker"],
    )

    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER),
        patch(
            "app.services.resume_service.GeminiAIAdapter.analyze_job",
            return_value=mock_analysis,
        ),
    ):
        res = await async_client.post(
            "/api/v1/resumes/match-preview",
            headers=headers,
            json={"job_description": "Vaga para desenvolvedor Python com conhecimento em Docker."},
        )
        assert res.status_code == 200
        data = res.json()
        assert "match_percentage" in data
        assert data["match_percentage"] > 0
        assert len(data["mandatory_matches"]) == 1
        assert data["mandatory_matches"][0]["requirement"] == "Python"
        assert data["mandatory_matches"][0]["status"] == "matched"
