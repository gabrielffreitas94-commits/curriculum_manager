"""Testes unitários para a porta de IA e adaptador Gemini."""

from unittest.mock import patch

import pytest

from app.adapters.gemini_ai_adapter import GeminiAIAdapter
from app.ports.ai_port import (
    FullGeneratedResumePayload,
    JobAnalysisResult,
    MissingApiKeyError,
)


@pytest.mark.asyncio
async def test_missing_api_key_raises_error() -> None:
    """Garante que a falta de API Key do Gemini levante MissingApiKeyError."""
    adapter = GeminiAIAdapter(api_key=None)
    with pytest.raises(MissingApiKeyError, match="Chave de API do Gemini não configurada"):
        await adapter.analyze_job("Job description without key")


@pytest.mark.asyncio
async def test_analyze_job_success() -> None:
    """Testa a extração estruturada de requisitos de vaga."""
    adapter = GeminiAIAdapter(api_key="AIzaFakeKeyTesting")

    mock_analysis = JobAnalysisResult(
        job_title="Software Architect",
        seniority_level="Senior",
        mandatory_requirements=["Python", "FastAPI"],
        desirable_requirements=["Kubernetes"],
        keywords=["REST", "Cloud", "Microservices"],
    )

    with patch.object(adapter, "analyze_job", return_value=mock_analysis):
        result = await adapter.analyze_job("Python Architect needed.")
        assert result.job_title == "Software Architect"
        assert "Python" in result.mandatory_requirements
        assert "Kubernetes" in result.desirable_requirements


@pytest.mark.asyncio
async def test_generate_resume_structured_output() -> None:
    """Testa a geração estruturada compatível com FullGeneratedResumePayload."""
    adapter = GeminiAIAdapter(api_key="AIzaFakeKeyTesting")

    mock_payload = FullGeneratedResumePayload(
        header={
            "full_name": "João da Silva",
            "target_title": "Senior Software Engineer",
            "email": "joao@email.com",
            "phone": "+55 11 99999-9999",
            "location": "São Paulo, SP",
            "links": {"github": "https://github.com/joao"},
        },
        professional_summary="Especialista em Python e microsserviços.",
        selected_experiences=[
            {
                "company_name": "Tech Corp",
                "position_title": "Backend Lead",
                "start_date": "2020-01-01",
                "end_date": None,
                "is_current": True,
                "description": "Desenvolvimento de APIs",
                "bullet_points": ["Otimizou throughput"],
                "tech_stack": ["Python", "PostgreSQL"],
                "quantifiable_results": ["40% mais rápido"],
                "sort_order": 0,
            }
        ],
        skills_highlighted=["Python", "PostgreSQL"],
        education=[],
        certifications=[],
        projects=[],
        languages=[],
        match_analysis={
            "mandatory_requirements": [
                {"requirement": "Python", "status": "matched", "evidence": "Experiência comprovada"}
            ],
            "desirable_requirements": [],
        },
        match_percentage=95.0,
    )

    with patch.object(adapter, "generate_resume", return_value=mock_payload):
        result = await adapter.generate_resume(
            job_description="Python Senior",
            user_dossier={"skills": ["Python"]},
            prompt_skill_instructions="Foco técnico.",
            language="pt-BR",
        )
        assert result.header["full_name"] == "João da Silva"
        assert result.match_percentage == 95.0
        assert len(result.selected_experiences) == 1
