"""Testes unitários para a telemetria de adaptadores e domínio (Fase 3).

Valida a emissão estruturada de métricas de GenAI (tokens, latência, modelos),
diagnóstico algorítmico do GroundingAuditEngine e métricas de renderização de PDF/DOCX.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.docx_adapter import DocxAdapter
from app.adapters.gemini_ai_adapter import GeminiAIAdapter
from app.adapters.weasyprint_adapter import WeasyPrintAdapter
from app.core.grounding_audit import GroundingAuditEngine
from app.ports.ai_port import AIError, GenerationError


@pytest.fixture
def dummy_job_analysis_json() -> str:
    """Retorna JSON válido de análise de vaga."""
    return json.dumps(
        {
            "job_title": "Senior Python Engineer",
            "seniority_level": "Senior",
            "mandatory_requirements": ["Python", "FastAPI"],
            "desirable_requirements": ["GCP", "Kubernetes"],
            "keywords": ["Clean Architecture", "OTel"],
        }
    )


@pytest.fixture
def dummy_resume_payload_json() -> str:
    """Retorna JSON estruturado válido de FullGeneratedResumePayload."""
    return json.dumps(
        {
            "header": {
                "full_name": "Ana Souza",
                "target_title": "Engenheira de Dados Senior",
                "email": "ana.souza@exemplo.com",
            },
            "professional_summary": "Especialista em pipelines escaláveis.",
            "selected_experiences": [
                {
                    "company_name": "DataCorp",
                    "position_title": "Data Engineer",
                    "tech_stack": ["Python", "SQL"],
                    "bullet_points": ["Construiu data lakehouse."],
                }
            ],
            "skills_highlighted": ["Python", "SQL"],
            "education": [],
            "certifications": [],
            "projects": [],
            "languages": [],
            "match_analysis": {},
            "match_percentage": 92.5,
            "provenance_map": {"Python": "Python", "SQL": "SQL"},
        }
    )


# ==============================================================================
# 1. TESTES DE TELEMETRIA DO GEMINI AI ADAPTER
# ==============================================================================


@pytest.mark.asyncio
async def test_gemini_analyze_job_telemetry_success(
    capsys: pytest.CaptureFixture[str],
    dummy_job_analysis_json: str,
):
    """Valida emissão de log de métricas de tokens e latência no analyze_job com sucesso."""
    adapter = GeminiAIAdapter(api_key="test-api-key")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = dummy_job_analysis_json

    # Configura contadores de tokens no mock
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 120
    mock_usage.candidates_token_count = 65
    mock_usage.total_token_count = 185
    mock_response.usage_metadata = mock_usage

    mock_client.models.generate_content.return_value = mock_response
    adapter._client = mock_client

    result = await adapter.analyze_job("Anúncio de vaga detalhado...")
    assert result.job_title == "Senior Python Engineer"

    captured = capsys.readouterr().out
    assert "gemini_job_analysis_completed" in captured
    assert "model=gemini-1.5-flash" in captured or '"model": "gemini-1.5-flash"' in captured
    assert "prompt_tokens=120" in captured or '"prompt_tokens": 120' in captured
    assert "candidates_tokens=65" in captured or '"candidates_tokens": 65' in captured
    assert "total_tokens=185" in captured or '"total_tokens": 185' in captured
    assert "duration_ms=" in captured or '"duration_ms":' in captured


@pytest.mark.asyncio
async def test_gemini_analyze_job_telemetry_empty_response(
    capsys: pytest.CaptureFixture[str],
):
    """Valida emissão de log de erro estruturado quando o Gemini retorna resposta vazia."""
    adapter = GeminiAIAdapter(api_key="test-api-key")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = ""
    mock_client.models.generate_content.return_value = mock_response
    adapter._client = mock_client

    with pytest.raises(GenerationError, match="resposta vazia"):
        await adapter.analyze_job("Anúncio de vaga...")

    captured = capsys.readouterr().out
    assert "gemini_job_analysis_empty_response" in captured
    assert "gemini-1.5-flash" in captured


@pytest.mark.asyncio
async def test_gemini_analyze_job_telemetry_api_failure(
    capsys: pytest.CaptureFixture[str],
):
    """Valida emissão de log com error_type e error_message em caso de falha da API."""
    adapter = GeminiAIAdapter(api_key="test-api-key")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = ConnectionResetError(
        "Conexão interrompida pelo host"
    )
    adapter._client = mock_client

    with pytest.raises(AIError, match="Falha na análise semântica"):
        await adapter.analyze_job("Anúncio...")

    captured = capsys.readouterr().out
    assert "gemini_job_analysis_failed" in captured
    assert "ConnectionResetError" in captured
    assert "Conexão interrompida" in captured


@pytest.mark.asyncio
async def test_gemini_generate_resume_telemetry_success(
    capsys: pytest.CaptureFixture[str],
    dummy_resume_payload_json: str,
):
    """Valida log de conclusão da síntese de currículo com contadores e match_percentage."""
    adapter = GeminiAIAdapter(api_key="test-api-key")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = dummy_resume_payload_json

    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 450
    mock_usage.candidates_token_count = 320
    mock_usage.total_token_count = 770
    mock_response.usage_metadata = mock_usage

    mock_client.models.generate_content.return_value = mock_response
    adapter._client = mock_client

    payload = await adapter.generate_resume(
        job_description="Vaga Eng Dados",
        user_dossier={"skills": ["Python", "SQL"]},
        prompt_skill_instructions="Instruções",
        language="pt-BR",
    )

    assert payload.match_percentage == 92.5

    captured = capsys.readouterr().out
    assert "gemini_resume_generation_completed" in captured
    assert "prompt_tokens=450" in captured or '"prompt_tokens": 450' in captured
    assert "candidates_tokens=320" in captured or '"candidates_tokens": 320' in captured
    assert "total_tokens=770" in captured or '"total_tokens": 770' in captured
    assert "match_percentage=92.5" in captured or '"match_percentage": 92.5' in captured


@pytest.mark.asyncio
async def test_gemini_generate_resume_telemetry_empty_response(
    capsys: pytest.CaptureFixture[str],
):
    """Valida log de erro quando a geração de currículo vem vazia."""
    adapter = GeminiAIAdapter(api_key="test-api-key")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = ""
    mock_client.models.generate_content.return_value = mock_response
    adapter._client = mock_client

    with pytest.raises(GenerationError, match="conteúdo vazio"):
        await adapter.generate_resume("Vaga", {}, "Prompt")

    captured = capsys.readouterr().out
    assert "gemini_resume_generation_empty_response" in captured


@pytest.mark.asyncio
async def test_gemini_generate_resume_telemetry_failure(
    capsys: pytest.CaptureFixture[str],
):
    """Valida captura e logging de exceção na síntese estruturada."""
    adapter = GeminiAIAdapter(api_key="test-api-key")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = TimeoutError("Gateway Timeout")
    adapter._client = mock_client

    with pytest.raises(GenerationError, match="Falha na síntese estruturada"):
        await adapter.generate_resume("Vaga", {}, "Prompt")

    captured = capsys.readouterr().out
    assert "gemini_resume_generation_failed" in captured
    assert "TimeoutError" in captured


# ==============================================================================
# 2. TESTES DE TELEMETRIA DO GROUNDING AUDIT ENGINE
# ==============================================================================


def test_grounding_audit_engine_telemetry(
    capsys: pytest.CaptureFixture[str],
):
    """Valida log estruturado emitido pelo GroundingAuditEngine com métricas de tiers e score."""
    engine = GroundingAuditEngine()

    generated = {
        "selected_experiences": [
            {
                "company_name": "Google",
                "tech_stack": ["Python", "Kubernetes"],
            }
        ],
        "skills_highlighted": ["Python", "FastAPI"],
    }
    dossier = {
        "companies": ["Google"],
        "skills": ["Python", "FastAPI", "Kubernetes"],
    }

    result = engine.audit(generated, dossier)
    assert result.is_valid is True
    assert result.trust_score == 100.0

    captured = capsys.readouterr().out
    assert "grounding_audit_completed" in captured
    assert "is_valid=True" in captured or '"is_valid": true' in captured
    assert "trust_score=100.0" in captured or '"trust_score": 100.0' in captured
    assert "duration_ms=" in captured or '"duration_ms":' in captured


def test_grounding_sanitization_telemetry(
    capsys: pytest.CaptureFixture[str],
):
    """Valida log emitido ao sanitizar/podar termos não validados."""
    engine = GroundingAuditEngine()
    generated = {
        "skills_highlighted": ["Python", "HaskellInventada"],
    }
    dossier = {
        "skills": ["Python"],
    }

    audit_result = engine.audit(generated, dossier)
    # Limpa buffer do audit
    capsys.readouterr()

    sanitized = engine.sanitize(generated, audit_result)
    assert "HaskellInventada" not in sanitized["skills_highlighted"]

    captured = capsys.readouterr().out
    assert "grounding_sanitization_completed" in captured
    assert "pruned_skills_count=1" in captured or '"pruned_skills_count": 1' in captured


# ==============================================================================
# 3. TESTES DE TELEMETRIA DOS ADAPTADORES DE DOCUMENTOS
# ==============================================================================


def test_weasyprint_adapter_telemetry_success(
    capsys: pytest.CaptureFixture[str],
):
    """Valida log de renderização de PDF bem-sucedida com tamanho e latência."""
    adapter = WeasyPrintAdapter()

    fake_pdf = b"%PDF-1.4 Dummy Binary Content"
    mock_html = MagicMock()
    mock_html.write_pdf.return_value = fake_pdf
    mock_weasyprint = MagicMock(HTML=MagicMock(return_value=mock_html))

    with patch.dict("sys.modules", {"weasyprint": mock_weasyprint}):
        output = adapter.render_pdf("<html><body>Currículo</body></html>")

    assert output == fake_pdf
    captured = capsys.readouterr().out
    assert "pdf_rendered_successfully" in captured
    assert "document_type=pdf" in captured or '"document_type": "pdf"' in captured
    assert "pdf_size_bytes=" in captured or '"pdf_size_bytes":' in captured


def test_weasyprint_adapter_telemetry_missing_dependencies(
    capsys: pytest.CaptureFixture[str],
):
    """Valida log estruturado de erro quando as bibliotecas C nativas não estão disponíveis."""
    adapter = WeasyPrintAdapter()

    with (
        patch.dict("sys.modules", {"weasyprint": None}),
        pytest.raises(RuntimeError, match="requer bibliotecas C nativas"),
    ):
        adapter.render_pdf("<html><body>Currículo</body></html>")

    captured = capsys.readouterr().out
    assert "pdf_render_dependencies_missing" in captured
    assert "document_type=pdf" in captured or '"document_type": "pdf"' in captured


def test_docx_adapter_telemetry_success(
    capsys: pytest.CaptureFixture[str],
):
    """Valida log de renderização de DOCX com tamanho, idioma e duração em milissegundos."""
    adapter = DocxAdapter()
    resume_data = {
        "header": {"full_name": "Carlos Silva", "target_title": "Backend Architect"},
        "professional_summary": "Arquiteto de sistemas distribuídos.",
        "skills_highlighted": ["Python", "FastAPI"],
    }

    docx_bytes = adapter.render_docx(resume_data, locale_code="pt-BR")
    assert len(docx_bytes) > 0

    captured = capsys.readouterr().out
    assert "docx_rendered_successfully" in captured
    assert "document_type=docx" in captured or '"document_type": "docx"' in captured
    assert "locale_code=pt-BR" in captured or '"locale_code": "pt-BR"' in captured
    assert "docx_size_bytes=" in captured or '"docx_size_bytes":' in captured
