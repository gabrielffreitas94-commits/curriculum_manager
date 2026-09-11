"""Testes unitários para o adaptador GeminiAIAdapter (Hexagonal Architecture).

Valida a integração real da classe consumindo o SDK google-genai através de mocks
da API externa (genai.Client), sem mascarar a lógica interna de parsing e exceções.
"""

import json
from unittest.mock import MagicMock

import pytest

from app.adapters.gemini_ai_adapter import GeminiAIAdapter
from app.ports.ai_port import (
    AIError,
    FullGeneratedResumePayload,
    GenerationError,
    MissingApiKeyError,
)


@pytest.mark.asyncio
async def test_missing_api_key_raises_error() -> None:
    """Garante que instanciar o adaptador sem API Key levante
    MissingApiKeyError em qualquer chamada.
    """
    adapter_none = GeminiAIAdapter(api_key=None)
    with pytest.raises(MissingApiKeyError, match="Chave de API do Gemini não configurada"):
        await adapter_none.analyze_job("Vaga desc")

    adapter_empty = GeminiAIAdapter(api_key="   ")
    with pytest.raises(MissingApiKeyError, match="Chave de API do Gemini não configurada"):
        await adapter_empty.generate_resume(
            job_description="Vaga desc",
            user_dossier={},
            prompt_skill_instructions="",
        )


@pytest.mark.asyncio
async def test_analyze_job_real_parsing_success() -> None:
    """Valida o método analyze_job executando parsing real de resposta JSON do Gemini."""
    adapter = GeminiAIAdapter(api_key="AIzaSyMockRealTestingKey123")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "job_title": "Staff Backend Engineer",
            "seniority_level": "Staff / Principal",
            "mandatory_requirements": ["Python", "FastAPI", "PostgreSQL"],
            "desirable_requirements": ["Kubernetes", "GCP"],
            "keywords": ["Microservices", "REST", "Scalability"],
        }
    )
    mock_client.models.generate_content.return_value = mock_response
    adapter._client = mock_client

    result = await adapter.analyze_job("Descrição completa da vaga de Staff Backend.")

    assert result.job_title == "Staff Backend Engineer"
    assert result.seniority_level == "Staff / Principal"
    assert "Python" in result.mandatory_requirements
    assert "Kubernetes" in result.desirable_requirements
    assert "Scalability" in result.keywords
    assert mock_client.models.generate_content.called


@pytest.mark.asyncio
async def test_analyze_job_empty_response_raises_generation_error() -> None:
    """Garante que uma resposta vazia do Gemini na análise de vaga levante GenerationError."""
    adapter = GeminiAIAdapter(api_key="AIzaSyMockRealTestingKey123")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = ""
    mock_client.models.generate_content.return_value = mock_response
    adapter._client = mock_client

    with pytest.raises(GenerationError, match="Gemini retornou uma resposta vazia"):
        await adapter.analyze_job("Vaga qualquer")


@pytest.mark.asyncio
async def test_analyze_job_api_failure_raises_aierror() -> None:
    """Garante que falhas de rede ou serviço da API Google GenAI levantem AIError."""
    adapter = GeminiAIAdapter(api_key="AIzaSyMockRealTestingKey123")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("503 Service Unavailable")
    adapter._client = mock_client

    with pytest.raises(AIError, match="503 Service Unavailable"):
        await adapter.analyze_job("Vaga qualquer")


@pytest.mark.asyncio
async def test_generate_resume_real_parsing_success() -> None:
    """Valida generate_resume executando serialização de prompt e deserialização de payload real."""
    adapter = GeminiAIAdapter(api_key="AIzaSyMockRealTestingKey123")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "header": {
                "full_name": "Ana Clara Dev",
                "target_title": "Lead Python Engineer",
                "email": "ana@thothcvs.ai",
                "phone": "+55 11 99999-8888",
                "location": "São Paulo, SP",
                "links": {"github": "https://github.com/anaclara"},
            },
            "professional_summary": "Especialista em microsserviços escaláveis e Python.",
            "selected_experiences": [
                {
                    "company_name": "InovaTech",
                    "position_title": "Senior Python Architect",
                    "start_date": "2021-01-01",
                    "end_date": None,
                    "is_current": True,
                    "description": "Liderança técnica de microsserviços.",
                    "bullet_points": ["Otimizou o throughput em 45%."],
                    "tech_stack": ["Python", "FastAPI", "Docker"],
                    "quantifiable_results": ["Economia de 30% em cloud"],
                    "sort_order": 0,
                }
            ],
            "skills_highlighted": ["Python", "FastAPI", "PostgreSQL"],
            "education": [
                {
                    "institution": "USP",
                    "degree": "Bacharelado em Ciência da Computação",
                    "start_date": "2016-01-01",
                    "end_date": "2020-12-01",
                }
            ],
            "certifications": [
                {
                    "name": "Google Cloud Professional Architect",
                    "issuer": "Google",
                    "issue_date": "2022-05-01",
                }
            ],
            "projects": [],
            "languages": [{"language": "Português", "proficiency": "Nativo"}],
            "match_analysis": {
                "mandatory_requirements": [
                    {"requirement": "Python", "status": "matched", "evidence": "InovaTech"}
                ],
                "desirable_requirements": [],
            },
            "match_percentage": 94.5,
            "provenance_map": {"Python": "Python"},
        }
    )
    mock_client.models.generate_content.return_value = mock_response
    adapter._client = mock_client

    user_dossier = {
        "companies": ["InovaTech"],
        "skills": ["Python", "FastAPI"],
    }

    result = await adapter.generate_resume(
        job_description="Vaga Lead Python",
        user_dossier=user_dossier,
        prompt_skill_instructions="Seja conciso.",
        language="pt-BR",
    )

    assert isinstance(result, FullGeneratedResumePayload)
    assert result.header["full_name"] == "Ana Clara Dev"
    assert result.match_percentage == 94.5
    assert len(result.selected_experiences) == 1
    assert result.provenance_map["Python"] == "Python"


@pytest.mark.asyncio
async def test_generate_resume_empty_response_raises_generation_error() -> None:
    """Garante que resposta sem texto levante GenerationError."""
    adapter = GeminiAIAdapter(api_key="AIzaSyMockRealTestingKey123")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = ""
    mock_client.models.generate_content.return_value = mock_response
    adapter._client = mock_client

    with pytest.raises(GenerationError, match="Gemini retornou conteúdo vazio"):
        await adapter.generate_resume(
            job_description="Vaga",
            user_dossier={},
            prompt_skill_instructions="",
        )


@pytest.mark.asyncio
async def test_generate_resume_malformed_json_raises_generation_error() -> None:
    """Garante que JSON inválido gerado pelo Gemini levante GenerationError."""
    adapter = GeminiAIAdapter(api_key="AIzaSyMockRealTestingKey123")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "NOT A VALID JSON RESPONSE"
    mock_client.models.generate_content.return_value = mock_response
    adapter._client = mock_client

    with pytest.raises(GenerationError, match="Falha na síntese estruturada do currículo"):
        await adapter.generate_resume(
            job_description="Vaga",
            user_dossier={},
            prompt_skill_instructions="",
        )
