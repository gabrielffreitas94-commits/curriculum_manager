"""Testes de integração para as rotas do motor de geração de currículos (Gemini)."""

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.ports.ai_port import FullGeneratedResumePayload, JobAnalysisResult
from app.ports.auth_port import AuthUser

TEST_USER_AUTH = AuthUser(
    uid="firebase_gemini_user_1",
    email="gemini_tester@thothcvs.ai",
    full_name="Carlos Gemini",
)


@pytest.fixture
async def setup_resume_user(async_client: AsyncClient) -> dict[str, str]:
    """Cria o usuário com experiências pré-cadastradas para o teste de geração."""
    headers = {"Authorization": "Bearer gemini_token"}

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=TEST_USER_AUTH):
        # 1. Sync User
        res = await async_client.post(
            "/api/v1/auth/sync",
            headers=headers,
            json={"target_title": "Senior Cloud Engineer"},
        )
        assert res.status_code == 200

        # 2. Add API Key in Settings
        res_settings = await async_client.put(
            "/api/v1/users/me/settings",
            headers=headers,
            json={"gemini_api_key": "AIzaSyMockKeyForGeminiTesting123"},
        )
        assert res_settings.status_code == 200

        # 3. Add Experience
        res_exp = await async_client.post(
            "/api/v1/profile/experiences",
            headers=headers,
            json={
                "company_name": "CloudWorks",
                "position_title": "Cloud Architect",
                "work_model": "remote",
                "start_date": "2021-01-01",
                "description": "Liderança de projetos GCP.",
                "tech_stack": ["Python", "FastAPI", "GCP", "Terraform"],
            },
        )
        assert res_exp.status_code == 201

        # 4. Add Skills
        res_skill = await async_client.post(
            "/api/v1/profile/skills",
            headers=headers,
            json={"name": "Python", "category": "backend", "proficiency_level": "expert"},
        )
        assert res_skill.status_code == 201

    return {"headers": headers}


@pytest.mark.asyncio
async def test_analyze_job_endpoint(
    async_client: AsyncClient,
    setup_resume_user: dict,
) -> None:
    """Testa a rota de análise semântica de requisitos de vaga."""
    headers = setup_resume_user["headers"]

    mock_analysis = JobAnalysisResult(
        job_title="Senior GCP Architect",
        seniority_level="Senior",
        mandatory_requirements=["Python", "GCP"],
        desirable_requirements=["Terraform"],
        keywords=["Cloud", "DevOps"],
    )

    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", return_value=TEST_USER_AUTH),
        patch(
            "app.services.resume_service.GeminiAIAdapter.analyze_job",
            return_value=mock_analysis,
        ),
    ):
        res = await async_client.post(
            "/api/v1/resumes/analyze-job",
            headers=headers,
            json={"job_description": "Precisa-se de Senior GCP Architect com Python e GCP."},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["job_title"] == "Senior GCP Architect"
        assert "Python" in data["mandatory_requirements"]


@pytest.mark.asyncio
async def test_generate_resume_full_pipeline(
    async_client: AsyncClient,
    setup_resume_user: dict,
) -> None:
    """Testa o pipeline completo de 4 estágios gerando o currículo e vinculando à candidatura."""
    headers = setup_resume_user["headers"]

    mock_resume_payload = FullGeneratedResumePayload(
        header={
            "full_name": "Carlos Gemini",
            "target_title": "Senior GCP Architect",
            "email": "gemini_tester@thothcvs.ai",
            "phone": "+55 11 99999-9999",
            "location": "São Paulo, SP",
            "links": {},
        },
        professional_summary="Especialista em Cloud GCP e Python com vasta experiência.",
        selected_experiences=[
            {
                "company_name": "CloudWorks",
                "position_title": "Cloud Architect",
                "start_date": "2021-01-01",
                "end_date": None,
                "is_current": True,
                "description": "Projetos GCP em larga escala.",
                "bullet_points": ["Implementou infraestrutura GCP resiliente."],
                "tech_stack": ["Python", "FastAPI", "GCP", "Terraform"],
                "quantifiable_results": [],
                "sort_order": 0,
            }
        ],
        skills_highlighted=["Python", "GCP", "Terraform"],
        education=[],
        certifications=[],
        projects=[],
        languages=[],
        match_analysis={
            "mandatory_requirements": [
                {
                    "requirement": "GCP",
                    "status": "matched",
                    "evidence": "Experiência na CloudWorks",
                }
            ],
            "desirable_requirements": [],
        },
        match_percentage=92.0,
    )

    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", return_value=TEST_USER_AUTH),
        patch(
            "app.services.resume_service.GeminiAIAdapter.generate_resume",
            return_value=mock_resume_payload,
        ),
    ):
        res = await async_client.post(
            "/api/v1/resumes/generate",
            headers=headers,
            json={
                "job_description": "Vaga Cloud Architect com Python e GCP",
                "prompt_skill_slug": "tech-startup",
                "language": "pt-BR",
                "create_application": True,
                "company_name": "CloudCorp",
                "job_title": "Cloud Architect",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["resume_id"] is not None
        assert data["application_id"] is not None
        assert data["match_percentage"] == 92.0
        assert data["structured_content"]["header"]["full_name"] == "Carlos Gemini"
        assert len(data["structured_content"]["selected_experiences"]) == 1


@pytest.mark.asyncio
async def test_generate_resume_hallucination_rejected(
    async_client: AsyncClient,
    setup_resume_user: dict,
) -> None:
    """Garante que a rota retorne 422 caso a IA forje empresas não cadastradas."""
    headers = setup_resume_user["headers"]

    hallucinated_payload = FullGeneratedResumePayload(
        header={"full_name": "Carlos Gemini"},
        professional_summary="Texto com empresa inventada",
        selected_experiences=[
            {
                "company_name": "Empresa Fantasma Inexistente",  # Alucinação crítica
                "position_title": "Fake Role",
                "start_date": "2020-01-01",
                "description": "Atividades inventadas",
                "tech_stack": [],
                "bullet_points": [],
                "quantifiable_results": [],
                "sort_order": 0,
            }
        ],
        skills_highlighted=[],
        education=[],
        certifications=[],
        projects=[],
        languages=[],
        match_analysis={},
        match_percentage=10.0,
    )

    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", return_value=TEST_USER_AUTH),
        patch(
            "app.services.resume_service.GeminiAIAdapter.generate_resume",
            return_value=hallucinated_payload,
        ),
    ):
        res = await async_client.post(
            "/api/v1/resumes/generate",
            headers=headers,
            json={
                "job_description": "Vaga com requisitos normais",
                "prompt_skill_slug": "tech-startup",
                "language": "pt-BR",
                "create_application": True,
                "company_name": "Company X",
                "job_title": "Role Y",
            },
        )
        assert res.status_code == 422
        assert "Geração rejeitada pelo motor anti-alucinação" in res.json()["detail"]


@pytest.mark.asyncio
async def test_generate_resume_concurrency_lock(
    async_client: AsyncClient,
    setup_resume_user: dict,
) -> None:
    """Garante que requisições concorrentes da mesma conta retornem 409 Conflict."""
    headers = setup_resume_user["headers"]

    from app.services.resume_service import _ACTIVE_GENERATIONS

    # Simula geração já ativa para o usuário
    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=TEST_USER_AUTH):
        # Primeiro busca o usuário para obter seu UUID
        user_res = await async_client.post("/api/v1/auth/sync", headers=headers)
        user_id = uuid.UUID(user_res.json()["id"])

        _ACTIVE_GENERATIONS.add(user_id)
        try:
            res = await async_client.post(
                "/api/v1/resumes/generate",
                headers=headers,
                json={
                    "job_description": "Vaga concorrente de teste com mais de vinte caracteres.",
                    "prompt_skill_slug": "tech-startup",
                },
            )
            assert res.status_code == 409
            assert "GENERATION_ALREADY_IN_PROGRESS" in res.json()["detail"]
        finally:
            _ACTIVE_GENERATIONS.discard(user_id)
