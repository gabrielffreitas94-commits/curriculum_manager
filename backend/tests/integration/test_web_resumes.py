"""Testes de integração para as rotas web do Gerador de Currículo e Copilot (app/api/web.py).

Valida a renderização HTML do wizard de tailoring, extração multimodal de vagas,
cálculo de aderência ATS e chat conversacional com guardrails de segurança.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.api.v1.schemas.resume import (
    MatchAnalysisItemSchema,
    MatchPreviewResponse,
    ResumeGenerateResponse,
)
from app.core.url_scraper import URLScraperError
from app.domain.models import PromptSkill, User

MOCK_USER_ID = uuid.uuid4()
MOCK_WEB_USER = User(
    id=MOCK_USER_ID,
    firebase_uid="firebase_resume_tester_uid",
    email="resume_tester@thothcvs.ai",
    full_name="Carlos Tailor",
    target_title="Senior Python Architect",
    phone="+55 11 99999-8888",
    location="São Paulo, SP",
    linkedin_url="https://linkedin.com/in/carlostailor",
    github_url="https://github.com/carlostailor",
)


@pytest.mark.asyncio
async def test_guardrail_new_resume_page_unauthenticated_redirects(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed que redireciona acessos anônimos à página de novo currículo.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Uso indevido de cotas de IA e visualização de interfaces privilegiadas.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Requisições sem cookie de sessão DEVEM ser redirecionadas com HTTP 302 para '/?auth_error=login_required'.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Afrouxar a dependência para permitir visitantes anônimos geraria exceções 500 no carregamento de skills.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Acesso anônimo a GET /resumes/new DEVE responder com HTTP 302 e header Location correspondente.
    """
    res = await async_client.get("/resumes/new", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=login_required"


@pytest.mark.asyncio
async def test_new_resume_page_authenticated_renders(async_client: AsyncClient) -> None:
    """Valida renderização completa da página de novo currículo para usuário autenticado."""
    async_client.cookies.set("session_token", "valid_session_token")
    mock_skill = PromptSkill(
        id=uuid.uuid4(),
        slug="google-xyz",
        name="Google XYZ",
        description="Foco em métricas",
        category="methodology",
        system_prompt="Regras Google",
        is_system_default=True,
    )
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.prompt_skill_service.PromptSkillService.list_active_skills",
            new_callable=AsyncMock,
            return_value=[mock_skill],
        ),
    ):
        res = await async_client.get("/resumes/new")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        content = res.text
        assert "Gerador de Currículo Sob Medida" in content
        assert "Oportunidade Alvo" in content
        assert "Google XYZ" in content
        assert "Método STAR" in content
        assert "Copilot Estratégico de IA" in content


@pytest.mark.asyncio
async def test_guardrail_scrape_job_url_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed que rejeita requisição de scraping sem sessão.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Abuso do motor de scraping como proxy anônimo na internet.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Chamadas a POST /resumes/scrape-job-url sem autenticação DEVEM responder HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Deixar a rota aberta sem auth expõe o scraper a scanners e botnets maliciosos.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST sem sessão DEVE retornar exatamente status 401 com script de redirecionamento.
    """
    res = await async_client.post(
        "/resumes/scrape-job-url", data={"url": "https://example.com/job"}
    )
    assert res.status_code == 401
    assert "window.location.href" in res.text


@pytest.mark.asyncio
async def test_guardrail_scrape_job_url_ssrf_blocked(async_client: AsyncClient) -> None:
    """Valida barreira fail-closed bloqueando URLs maliciosas e tratando exceções com segurança.

    VETOR DE AMEAÇA:
    - CWE-918: Server-Side Request Forgery (SSRF) / CWE-79: Cross-Site Scripting (XSS).
    - Impacto Potencial: Acesso a metadados de nuvem e injeção de HTML malicioso na mensagem de erro.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - URLs que tentem acessar redes privadas DEVEM disparar HTTP 400 com mensagem sanitizada e sem bypass.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Desabilitar a validação ou concatenar a mensagem de erro crua permitiria XSS e vazamento de rede interna.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - URL maliciosa que lance URLScraperError DEVE responder HTTP 400 com escaping de HTML.
    """
    async_client.cookies.set("session_token", "valid_session_token")
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.job_ingest_service.JobIngestService.extract_text_from_url",
            new_callable=AsyncMock,
            side_effect=URLScraperError(
                "SSRF_SECURITY_ALERT: Acesso ao host 169.254.169.254 bloqueado."
            ),
        ),
    ):
        res = await async_client.post(
            "/resumes/scrape-job-url",
            data={"url": "http://169.254.169.254/latest/meta-data/"},
        )
        assert res.status_code == 400
        assert "Falha ao extrair vaga" in res.text
        assert "SSRF_SECURITY_ALERT" in res.text


@pytest.mark.asyncio
async def test_scrape_job_url_success(async_client: AsyncClient) -> None:
    """Valida extração bem-sucedida de vaga por URL e retorno do script de preenchimento."""
    async_client.cookies.set("session_token", "valid_session_token")
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.job_ingest_service.JobIngestService.extract_text_from_url",
            new_callable=AsyncMock,
            return_value="Vaga Senior Python Engineer com FastAPI e PostgreSQL.",
        ),
    ):
        res = await async_client.post(
            "/resumes/scrape-job-url",
            data={"url": "https://remotework.com/jobs/senior-python"},
        )
        assert res.status_code == 200
        assert "job-description-input" in res.text
        assert "Conteúdo da vaga importado com sucesso" in res.text


@pytest.mark.asyncio
async def test_guardrail_upload_job_doc_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed que rejeita upload de documento de vaga sem sessão.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Processamento computacional pesado de arquivos não autorizados.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Chamadas anônimas a POST /resumes/upload-job-doc DEVEM responder HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Permitir upload anônimo esgotaria recursos de CPU com parsing de documentos arbitrários.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Upload sem cookie de sessão DEVE responder exatamente HTTP 401 com script de redirecionamento.
    """
    files = {"file": ("job.pdf", b"%PDF-1.4 dummy", "application/pdf")}
    res = await async_client.post("/resumes/upload-job-doc", files=files)
    assert res.status_code == 401
    assert "window.location.href" in res.text


@pytest.mark.asyncio
async def test_upload_job_doc_invalid_file_returns_400(async_client: AsyncClient) -> None:
    """Valida rejeição de arquivo inválido de vaga com HTTP 400 e mensagem explicativa."""
    async_client.cookies.set("session_token", "valid_session_token")
    with patch(
        "app.services.auth_service.AuthService.get_authenticated_user",
        new_callable=AsyncMock,
        return_value=MOCK_WEB_USER,
    ):
        files = {"file": ("payload.exe", b"MZexecutable", "application/octet-stream")}
        res = await async_client.post("/resumes/upload-job-doc", files=files)
        assert res.status_code == 400
        assert "Falha ao ler documento" in res.text


@pytest.mark.asyncio
async def test_upload_job_doc_success(async_client: AsyncClient) -> None:
    """Valida extração bem-sucedida de vaga por upload de documento (PDF/DOCX)."""
    async_client.cookies.set("session_token", "valid_session_token")
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.job_ingest_service.JobIngestService.extract_text_from_document",
            return_value="Descrição da vaga extraída do PDF com sucesso.",
        ),
    ):
        files = {"file": ("vaga.pdf", b"%PDF-1.4 content", "application/pdf")}
        res = await async_client.post("/resumes/upload-job-doc", files=files)
        assert res.status_code == 200
        assert "job-description-input" in res.text
        assert "Documento processado com sucesso" in res.text


@pytest.mark.asyncio
async def test_guardrail_analyze_match_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed que rejeita análise de aderência sem usuário logado.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Disparo indevido de inferência vetorial/semântica sem permissão.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - POST /resumes/analyze-match sem autenticação DEVE responder HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Omitir o gate de autenticação permitiria negação de serviço e computação indevida de embeddings.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Acesso anônimo a POST /resumes/analyze-match DEVE retornar status 401.
    """
    res = await async_client.post("/resumes/analyze-match", data={"job_description": "Vaga Python"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_analyze_match_empty_description_returns_400(async_client: AsyncClient) -> None:
    """Valida que solicitação de match sem texto de vaga retorna HTTP 400 e alerta."""
    async_client.cookies.set("session_token", "valid_session_token")
    with patch(
        "app.services.auth_service.AuthService.get_authenticated_user",
        new_callable=AsyncMock,
        return_value=MOCK_WEB_USER,
    ):
        res = await async_client.post("/resumes/analyze-match", data={"job_description": "   "})
        assert res.status_code == 400
        assert "informe a descrição da vaga" in res.text


@pytest.mark.asyncio
async def test_analyze_match_success_renders_card(async_client: AsyncClient) -> None:
    """Valida avaliação de fit ATS renderizando o template de match e lacunas."""
    async_client.cookies.set("session_token", "valid_session_token")
    mock_preview = MatchPreviewResponse(
        match_percentage=85.0,
        mandatory_matches=[
            MatchAnalysisItemSchema(
                requirement="Python",
                status="MATCH",
                evidence="10 anos de experiência com Python",
                similarity_score=0.95,
            )
        ],
        desirable_matches=[],
        missing_mandatory=["Kubernetes"],
        missing_desirable=[],
        suggested_keywords=["Python", "FastAPI"],
    )
    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.resume_service.ResumeService.match_preview",
            new_callable=AsyncMock,
            return_value=mock_preview,
        ),
    ):
        res = await async_client.post(
            "/resumes/analyze-match",
            data={"job_description": "Vaga Desenvolvedor Python com Kubernetes."},
        )
        assert res.status_code == 200
        assert "match-analysis-container" in res.text
        assert "85.0%" in res.text
        assert "Python" in res.text
        assert "Kubernetes" in res.text


@pytest.mark.asyncio
async def test_guardrail_copilot_chat_unauthenticated_returns_401(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed rejeitando interação com o Copilot sem autenticação.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Esgotamento de tokens e créditos na API de IA por usuários anônimos.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Chamadas ao chat sem sessão DEVEM responder com HTTP 401.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Permitir chat aberto sem credenciais consumiria cota da API de IA sem rastreabilidade.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /resumes/copilot-chat sem autenticação DEVE responder exatamente status 401.
    """
    res = await async_client.post("/resumes/copilot-chat", data={"message": "Olá"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_copilot_chat_empty_description_returns_400(async_client: AsyncClient) -> None:
    """Valida que mensagem ao Copilot sem vaga informada retorna HTTP 400 com aviso."""
    async_client.cookies.set("session_token", "valid_session_token")
    with patch(
        "app.services.auth_service.AuthService.get_authenticated_user",
        new_callable=AsyncMock,
        return_value=MOCK_WEB_USER,
    ):
        res = await async_client.post(
            "/resumes/copilot-chat",
            data={
                "message": "Como melhorar meu currículo?",
                "job_description": "",
                "prompt_skill_slug": "google-xyz",
            },
        )
        assert res.status_code == 400
        assert "descrição da vaga" in res.text


@pytest.mark.asyncio
async def test_copilot_chat_success_updates_history(async_client: AsyncClient) -> None:
    """Valida troca interativa de mensagens com o Copilot preservando histórico multi-turn."""
    async_client.cookies.set("session_token", "valid_session_token")
    mock_copilot = MagicMock()
    mock_copilot.chat = AsyncMock(
        return_value="Com a metodologia Google XYZ, quantifique seus resultados: 'Reduzi latência em 40%...'."
    )

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch("app.api.web.create_copilot_service", return_value=mock_copilot),
    ):
        history = [{"role": "assistant", "content": "Olá, sou seu copilot."}]
        res = await async_client.post(
            "/resumes/copilot-chat",
            data={
                "message": "Como reformular meus bullets para a vaga?",
                "job_description": "Vaga Tech Lead Python",
                "prompt_skill_slug": "google-xyz",
                "history_json": json.dumps(history),
            },
        )
        assert res.status_code == 200
        assert "copilot-chat-container" in res.text
        assert "Reduzi latência em 40%" in res.text
        assert "Como reformular meus bullets" in res.text


@pytest.mark.asyncio
async def test_copilot_chat_service_error_handled_gracefully(async_client: AsyncClient) -> None:
    """Valida tratamento seguro e sem quebra 500 caso o modelo de IA falhe."""
    async_client.cookies.set("session_token", "valid_session_token")
    mock_copilot = MagicMock()
    mock_copilot.chat = AsyncMock(side_effect=RuntimeError("Google Gemini API Timeout"))

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch("app.api.web.create_copilot_service", return_value=mock_copilot),
    ):
        res = await async_client.post(
            "/resumes/copilot-chat",
            data={
                "message": "Ajuda com a vaga",
                "job_description": "Vaga Python",
                "prompt_skill_slug": "google-xyz",
                "history_json": "[]",
            },
        )
        assert res.status_code == 200
        assert "Falha ao comunicar com o assistente de IA" in res.text
        assert "Google Gemini API Timeout" in res.text


@pytest.mark.asyncio
async def test_guardrail_generate_custom_unauthenticated_redirects(
    async_client: AsyncClient,
) -> None:
    """Valida barreira fail-closed que impede síntese anônima de currículo via POST.

    VETOR DE AMEAÇA:
    - CWE-306: Missing Authentication for Critical Function.
    - Impacto Potencial: Criação anônima de currículos no banco de dados e gasto de tokens.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Chamadas sem sessão DEVEM redirecionar para a tela inicial com 'login_required'.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Omitir a validação causaria escrita órfã de dados e vulnerabilidade de impersonação.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - POST /resumes/generate-custom sem usuário autenticado DEVE responder HTTP 302 para login.
    """
    res = await async_client.post(
        "/resumes/generate-custom",
        data={"job_description": "Vaga Python", "prompt_skill_slug": "google-xyz"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert res.headers["location"] == "/?auth_error=login_required"


@pytest.mark.asyncio
async def test_generate_custom_success_redirects_to_preview(async_client: AsyncClient) -> None:
    """Valida que geração de currículo personalizada redireciona para a visualização."""
    async_client.cookies.set("session_token", "valid_session_token")
    mock_resume_id = uuid.uuid4()
    mock_response = ResumeGenerateResponse(
        resume_id=mock_resume_id,
        application_id=uuid.uuid4(),
        version_number=1,
        match_percentage=90.0,
        match_analysis={},
        structured_content={
            "target_title": "Staff Engineer",
            "summary_statement": "Resumo de carreira",
        },
    )

    with (
        patch(
            "app.services.auth_service.AuthService.get_authenticated_user",
            new_callable=AsyncMock,
            return_value=MOCK_WEB_USER,
        ),
        patch(
            "app.services.resume_service.ResumeService.generate_resume",
            new_callable=AsyncMock,
            return_value=mock_response,
        ),
    ):
        res = await async_client.post(
            "/resumes/generate-custom",
            data={
                "job_description": "Vaga Senior Staff Engineer",
                "prompt_skill_slug": "google-xyz",
            },
            follow_redirects=False,
        )
        assert res.status_code == 302
        assert res.headers["location"] == f"/resumes/{mock_resume_id}/preview"
