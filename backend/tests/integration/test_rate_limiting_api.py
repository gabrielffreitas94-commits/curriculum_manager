"""Testes de integração para os guardrails de Rate Limiting nas rotas de IA."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import crypto_service
from app.core.rate_limit import limiter
from app.domain.models import Skill, User, UserSettings
from app.ports.ai_port import FullGeneratedResumePayload, JobAnalysisResult
from app.ports.auth_port import AuthUser

RATE_TEST_USER_ID = uuid.uuid4()

AUTH_USER = AuthUser(
    uid="rate_limit_user",
    email="rate_limit@example.com",
    full_name="Rate Limit Tester",
)


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    """Garante isolamento dos contadores de requisição entre cada teste."""
    limiter.reset()


@pytest.fixture
async def setup_rate_limit_user(db_session: AsyncSession) -> AsyncGenerator[dict[str, str], None]:
    """Cria o usuário com chave de API e competências para os testes de cota de requisição."""
    user = User(
        id=RATE_TEST_USER_ID,
        firebase_uid="rate_limit_user",
        email="rate_limit@example.com",
        full_name="Rate Limit Tester",
    )
    db_session.add(user)
    await db_session.flush()

    settings_obj = UserSettings(
        user_id=user.id,
        encrypted_gemini_api_key=crypto_service.encrypt(
            "AIzaSyMockKeyForRateLimitingTesting123",
            associated_data=str(user.id).encode("utf-8"),
        ),
    )
    db_session.add(settings_obj)

    skill = Skill(id=uuid.uuid4(), user_id=user.id, name="Python", category="Backend")
    db_session.add(skill)
    await db_session.commit()

    yield {"Authorization": "Bearer rate_limit_token"}


@pytest.mark.asyncio
async def test_analyze_job_rate_limiting_enforcement(
    async_client: AsyncClient,
    setup_rate_limit_user: dict[str, str],
) -> None:
    """Garante que a rota /analyze-job bloqueie rajadas após atingir o limite configurado (10/min).

    VETOR DE AMEAÇA:
    - OWASP A04:2021 (Insecure Design) / CWE-799 & OWASP LLM04:2025 (Model Denial of Service).
    - Impacto: Esgotamento financeiro de cotas da API Gemini e sobrecarga computacional.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Permite as primeiras 10 requisições (200 OK) e bloqueia a 11ª com status HTTP 429
      e cabeçalho Retry-After.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Se um desenvolvedor remover o decorator @limiter.limit ou a injeção do Request,
      o endpoint responderá ilimitadamente a requisições abusivas.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Dispara 11 chamadas em sequência; valida status 200 nas 10 primeiras e status 429
      na 11ª com header Retry-After == '60'.
    """
    headers = setup_rate_limit_user

    mock_analysis = JobAnalysisResult(
        job_title="Python Architect",
        seniority_level="Senior",
        mandatory_requirements=["Python"],
        desirable_requirements=["FastAPI"],
        keywords=["Python", "Cloud"],
    )

    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER),
        patch(
            "app.services.resume_service.GeminiAIAdapter.analyze_job",
            return_value=mock_analysis,
        ),
    ):
        for _ in range(10):
            res = await async_client.post(
                "/api/v1/resumes/analyze-job",
                headers=headers,
                json={
                    "job_description": (
                        "Vaga para desenvolvedor Python sênior com sólida experiência em FastAPI."
                    )
                },
            )
            assert res.status_code == 200

        blocked_res = await async_client.post(
            "/api/v1/resumes/analyze-job",
            headers=headers,
            json={
                "job_description": (
                    "Vaga para desenvolvedor Python sênior com sólida experiência em FastAPI."
                )
            },
        )
        assert blocked_res.status_code == 429
        assert blocked_res.headers.get("Retry-After") == "60"
        body = blocked_res.json()
        assert "10 per 1 minute" in body["error"]
        assert "Limite de requisições excedido" in body["detail"]


@pytest.mark.asyncio
async def test_match_preview_rate_limiting_enforcement(
    async_client: AsyncClient,
    setup_rate_limit_user: dict[str, str],
) -> None:
    """Garante que a rota /match-preview bloqueie requisições após o limite de 10/min.

    VETOR DE AMEAÇA:
    - OWASP A04:2021 (Insecure Design) / CWE-799 (Improper Control of Interaction Frequency).
    - Impacto: Abuso contínuo de inferência vetorial e parsing de competências sem síntese.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Permite as 10 requisições iniciais e bloqueia a 11ª com status HTTP 429.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Desativar rate limit nesta rota permitiria scraping abusivo de compatibilidade.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Executa 10 requisições seguidas com sucesso (200) e assere que a 11ª retorna 429.
    """
    headers = setup_rate_limit_user

    mock_analysis = JobAnalysisResult(
        job_title="Python Developer",
        seniority_level="Pleno",
        mandatory_requirements=["Python"],
        desirable_requirements=["Docker"],
        keywords=["Python"],
    )

    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER),
        patch(
            "app.services.resume_service.GeminiAIAdapter.analyze_job",
            return_value=mock_analysis,
        ),
    ):
        for _ in range(10):
            res = await async_client.post(
                "/api/v1/resumes/match-preview",
                headers=headers,
                json={"job_description": "Vaga Python pleno com foco em microsserviços e APIs."},
            )
            assert res.status_code == 200

        blocked_res = await async_client.post(
            "/api/v1/resumes/match-preview",
            headers=headers,
            json={"job_description": "Vaga Python pleno com foco em microsserviços e APIs."},
        )
        assert blocked_res.status_code == 429
        assert blocked_res.headers.get("Retry-After") == "60"


@pytest.mark.asyncio
async def test_generate_resume_rate_limiting_enforcement(
    async_client: AsyncClient,
    setup_rate_limit_user: dict[str, str],
) -> None:
    """Garante que a rota /generate bloqueie rajadas após atingir a cota restrita de 5/min.

    VETOR DE AMEAÇA:
    - OWASP LLM04:2025 (Model Denial of Service / Financial Exhaustion) & CWE-400 (DoS).
    - Impacto: A síntese completa do currículo consome múltiplos prompts encadeados e
      auditoria anti-alucinação; é o endpoint mais custoso computacional e financeiramente.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Limita estritamente a 5 requisições por minuto por IP, bloqueando a 6ª com 429.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Se a taxa for afrouxada para valores muito altos (ex: 100/min), bots poderiam
      gerar dezenas de currículos simultâneos, esgotando o limite de tokens da API Gemini.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Executa 5 chamadas com mock de retorno e assere que a 6ª requisição retorna HTTP 429.
    """
    headers = setup_rate_limit_user

    mock_payload = FullGeneratedResumePayload(
        header={
            "full_name": "Rate Tester",
            "target_title": "Software Architect",
            "email": "rate_limit@example.com",
            "phone": "+55 11 99999-9999",
            "location": "São Paulo, SP",
            "links": {},
        },
        professional_summary="Arquiteto com foco em soluções cloud e microsserviços.",
        selected_experiences=[
            {
                "company_name": "CloudWorks",
                "position_title": "Cloud Architect",
                "start_date": "2021-01-01",
                "end_date": None,
                "is_current": True,
                "description": "Projetos em nuvem.",
                "bullet_points": ["Microsserviços resilientes."],
                "tech_stack": ["Python"],
                "quantifiable_results": [],
                "sort_order": 0,
            }
        ],
        skills_highlighted=["Python"],
        education=[],
        certifications=[],
        projects=[],
        languages=[],
        match_analysis={},
        match_percentage=90.0,
    )

    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER),
        patch(
            "app.services.resume_service.GeminiAIAdapter.generate_resume",
            return_value=mock_payload,
        ),
        patch(
            "app.services.resume_service.GroundingAuditEngine.audit",
            return_value=MagicMock(is_valid=True, hallucinations=[]),
        ),
        patch(
            "app.services.resume_service.GroundingAuditEngine.sanitize",
            side_effect=lambda content, audit: content,
        ),
    ):
        for _ in range(5):
            res = await async_client.post(
                "/api/v1/resumes/generate",
                headers=headers,
                json={
                    "job_description": (
                        "Vaga para arquiteto de software cloud com domínio profundo de Python."
                    ),
                    "create_application": True,
                    "company_name": "CloudTech Corp",
                    "job_title": "Software Architect",
                },
            )
            assert res.status_code == 201

        blocked_res = await async_client.post(
            "/api/v1/resumes/generate",
            headers=headers,
            json={
                "job_description": (
                    "Vaga para arquiteto de software cloud com domínio profundo de Python."
                ),
                "create_application": True,
                "company_name": "CloudTech Corp",
                "job_title": "Software Architect",
            },
        )
        assert blocked_res.status_code == 429
        assert blocked_res.headers.get("Retry-After") == "60"
        body = blocked_res.json()
        assert "5 per 1 minute" in body["error"]
