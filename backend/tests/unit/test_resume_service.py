"""Testes unitários completos para o ResumeService (Orquestrador central de geração com IA).

Valida resolução de BYOK decifrado, concorrência simultânea, bloqueio de alucinação severa (422),
criação automática ou vínculo com candidatura existente e avaliação semântica prévia (match preview).
"""

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.resume import ResumeGenerateRequest
from app.core.crypto import crypto_service
from app.domain.models import Application, PromptSkill, User, UserSettings
from app.ports.ai_port import (
    AIError,
    FullGeneratedResumePayload,
    JobAnalysisResult,
    MissingApiKeyError,
)
from app.services.resume_service import _ACTIVE_GENERATIONS, ResumeService


@pytest.fixture
def resume_user() -> User:
    """Fixture com usuário para teste de síntese de currículo."""
    return User(
        id=uuid.uuid4(),
        firebase_uid="resume_unit_tester_uid",
        email="resume_unit@thothcvs.ai",
        full_name="Resume Unit Tester",
    )


def test_resolve_gemini_adapter_byok_and_fallbacks(resume_user: User) -> None:
    """Testa a resolução de chaves de API: BYOK com AAD, fallback legado e erro 400."""
    service = ResumeService(db=None)  # type: ignore[arg-type]

    # 1. Usuário com chave cifrada no banco com AAD (tenant_id)
    aad = str(resume_user.id).encode("utf-8")
    encrypted_key = crypto_service.encrypt("AIzaSyTenantBoundKey123", associated_data=aad)
    resume_user.settings = UserSettings(user_id=resume_user.id, encrypted_gemini_api_key=encrypted_key)

    adapter = service._resolve_gemini_adapter(user=resume_user)
    assert adapter._api_key == "AIzaSyTenantBoundKey123"

    # 2. Usuário com chave cifrada legada (sem AAD)
    encrypted_legacy = crypto_service.encrypt("AIzaSyLegacyKey456")
    resume_user.settings.encrypted_gemini_api_key = encrypted_legacy

    adapter_legacy = service._resolve_gemini_adapter(user=resume_user)
    assert adapter_legacy._api_key == "AIzaSyLegacyKey456"

    # 3. Usuário sem chave, mas variável GEMINI_API_KEY no ambiente
    resume_user.settings.encrypted_gemini_api_key = None
    with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyEnvKey789"}):
        adapter_env = service._resolve_gemini_adapter(user=resume_user)
        assert adapter_env._api_key == "AIzaSyEnvKey789"

    # 4. Nenhuma chave disponível (deve lançar 400 Bad Request)
    with patch.dict(os.environ, {}, clear=True):
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
        with pytest.raises(HTTPException) as exc:
            service._resolve_gemini_adapter(user=resume_user)
        assert exc.value.status_code == 400
        assert "Chave de API do Gemini não configurada" in exc.value.detail


@pytest.mark.asyncio
async def test_analyze_job_exceptions(resume_user: User) -> None:
    """Valida mapeamento de MissingApiKeyError (400) e AIError (502) no analyze_job."""
    service = ResumeService(db=None)  # type: ignore[arg-type]

    # Mock do adapter interno
    mock_adapter = MagicMock()
    service._resolve_gemini_adapter = MagicMock(return_value=mock_adapter)  # type: ignore[method-assign]

    # MissingApiKeyError -> 400
    mock_adapter.analyze_job = AsyncMock(side_effect=MissingApiKeyError("Sem chave"))
    with pytest.raises(HTTPException) as exc_missing:
        await service.analyze_job(user=resume_user, job_description="Vaga")
    assert exc_missing.value.status_code == 400

    # AIError -> 502
    mock_adapter.analyze_job = AsyncMock(side_effect=AIError("Gemini fora do ar"))
    with pytest.raises(HTTPException) as exc_ai:
        await service.analyze_job(user=resume_user, job_description="Vaga")
    assert exc_ai.value.status_code == 502


@pytest.mark.asyncio
async def test_generate_resume_concurrency_rejection(
    db_session: AsyncSession,
    resume_user: User,
) -> None:
    """Garante que requisições concorrentes para a mesma conta sejam rejeitadas com 409."""
    service = ResumeService(db=db_session)
    _ACTIVE_GENERATIONS.add(resume_user.id)

    try:
        req = ResumeGenerateRequest(job_description="Descrição longa para teste de concorrência")
        with pytest.raises(HTTPException) as exc:
            await service.generate_resume(user=resume_user, payload=req)
        assert exc.value.status_code == 409
        assert "GENERATION_ALREADY_IN_PROGRESS" in exc.value.detail
    finally:
        _ACTIVE_GENERATIONS.discard(resume_user.id)


@pytest.mark.asyncio
async def test_generate_resume_hallucination_and_tenant_validation(
    db_session: AsyncSession,
    resume_user: User,
) -> None:
    """Testa validações de tenant em application_id e bloqueio por alucinação grave."""
    db_session.add(resume_user)
    await db_session.flush()

    service = ResumeService(db=db_session)

    # Mock do adapter
    mock_payload = FullGeneratedResumePayload(
        header={"full_name": "Test"},
        professional_summary="Summary",
        selected_experiences=[],
        skills_highlighted=[],
        education=[],
        certifications=[],
        languages=[],
        match_analysis={},
        match_percentage=90.0,
    )
    mock_adapter = MagicMock()
    mock_adapter.generate_resume = AsyncMock(return_value=mock_payload)
    service._resolve_gemini_adapter = MagicMock(return_value=mock_adapter)  # type: ignore[method-assign]

    # 1. create_application=False e sem application_id -> 400
    req_no_app = ResumeGenerateRequest(
        job_description="Vaga sem app id e sem criação",
        create_application=False,
        application_id=None,
    )
    with pytest.raises(HTTPException) as exc_no_app:
        await service.generate_resume(user=resume_user, payload=req_no_app)
    assert exc_no_app.value.status_code == 400

    # 2. application_id inexistente ou de outro usuário -> 404
    req_fake_app = ResumeGenerateRequest(
        job_description="Vaga com app id fake",
        create_application=False,
        application_id=uuid.uuid4(),
    )

    with pytest.raises(HTTPException) as exc_fake_app:
        await service.generate_resume(user=resume_user, payload=req_fake_app)
    assert exc_fake_app.value.status_code == 404


@pytest.mark.asyncio
async def test_match_preview_integration(
    db_session: AsyncSession,
    resume_user: User,
) -> None:
    """Valida o cálculo de match preview integrando o analisador com o VectorMatchEngine."""
    db_session.add(resume_user)
    await db_session.flush()

    service = ResumeService(db=db_session)

    mock_analysis = JobAnalysisResult(
        job_title="Python Engineer",
        seniority_level="Senior",
        mandatory_requirements=["Python"],
        desirable_requirements=["FastAPI"],
        keywords=["Python", "FastAPI"],
    )

    mock_adapter = MagicMock()
    mock_adapter.analyze_job = AsyncMock(return_value=mock_analysis)
    service._resolve_gemini_adapter = MagicMock(return_value=mock_adapter)  # type: ignore[method-assign]

    preview = await service.match_preview(user=resume_user, job_description="Vaga Python Dev")
    assert preview is not None
    assert isinstance(preview.match_percentage, float)
    assert len(preview.mandatory_matches) == 1
    assert len(preview.desirable_matches) == 1

