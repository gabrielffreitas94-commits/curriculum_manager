"""Testes de integração para os endpoints de parsing e importação de currículo (/api/v1/profile).

Valida a segurança contra arquivos maliciosos, limites de tamanho e persistência
em lote no banco de dados com isolamento estrito de tenant.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.ports.auth_port import AuthUser
from app.ports.resume_parser_port import (
    ParsedExperienceDTO,
    ParsedPersonalDataDTO,
    ParsedProfileDTO,
    ParsedSkillDTO,
    ResumeParserError,
)

AUTH_USER = AuthUser(
    uid="firebase_user_import_test",
    email="import_tester@thothcvs.ai",
    full_name="Import Tester",
)


@pytest.fixture
async def auth_headers(async_client: AsyncClient) -> dict[str, str]:
    """Sincroniza o usuário no banco e retorna cabeçalho Authorization autenticado."""
    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER):
        res = await async_client.post(
            "/api/v1/auth/sync",
            headers={"Authorization": "Bearer token_import"},
        )
        assert res.status_code == 200
    return {"Authorization": "Bearer token_import"}


@pytest.mark.asyncio
async def test_guardrail_parse_resume_rejects_unsupported_file(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Valida rejeição fail-closed quando arquivo enviado possui extensão não permitida.

    VETOR DE AMEAÇA:
    - CWE-434: Unrestricted Upload of File with Dangerous Type.
    - Impacto Potencial: Envio de scripts maliciosos ou binários executáveis (.exe, .sh).

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O endpoint DEVE responder com HTTP 400 Bad Request detalhando formato não suportado.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Um refactor nos decorators do FastAPI que ignore o validador de arquivo repassaria
      a carga útil diretamente para o parser de IA.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Upload com filename='malware.exe' DEVE retornar exatamente HTTP 400.
    """
    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER):
        files = {"file": ("malware.exe", b"binarycontent", "application/octet-stream")}
        response = await async_client.post(
            "/api/v1/profile/parse-resume",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 400
        assert "não suportada" in response.json()["detail"]


@pytest.mark.asyncio
async def test_guardrail_parse_resume_rejects_oversized_file(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Valida proteção fail-closed contra exaustão de memória por arquivo gigante (DoS).

    VETOR DE AMEAÇA:
    - CWE-400: Uncontrolled Resource Consumption (Memory Exhaustion / DoS).
    - Impacto Potencial: Queda do servidor por consumo excessivo de memória ao ler
      arquivos descomunais.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O endpoint DEVE rejeitar com HTTP 413 Payload Too Large antes de enviar à IA.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Aumentar o limite sem controle ou remover a validação prévia de bytes.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Upload acima de 5 MB DEVE resultar em HTTP 413.
    """
    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER):
        huge_file_content = b"%PDF-" + b"0" * (5 * 1024 * 1024 + 10)
        files = {"file": ("large_resume.pdf", huge_file_content, "application/pdf")}
        response = await async_client.post(
            "/api/v1/profile/parse-resume",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 413
        assert "excede o limite" in response.json()["detail"]


@pytest.mark.asyncio
async def test_guardrail_parse_resume_rejects_spoofed_pdf(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Valida rejeição de arquivo renomeado como .pdf com magic bytes fraudulentos.

    VETOR DE AMEAÇA:
    - CWE-434 / Content Spoofing.
    - Impacto Potencial: Burla de filtros estáticos de extensão.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O validador identifica magic bytes inválidos e retorna HTTP 400.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Aceitar o MIME type 'application/pdf' enviado nos headers do cliente sem inspecionar bytes.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Payload b'NOT_A_PDF' nomeado como .pdf DEVE retornar HTTP 400 com erro de Magic Bytes.
    """
    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER):
        files = {"file": ("spoofed.pdf", b"NOT_A_PDF_CONTENT", "application/pdf")}
        response = await async_client.post(
            "/api/v1/profile/parse-resume",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 400
        assert "Magic Bytes" in response.json()["detail"]


@pytest.mark.asyncio
async def test_parse_resume_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Valida o fluxo com sucesso de envio e parsing de um currículo PDF."""
    mock_dto = ParsedProfileDTO(
        personal_data=ParsedPersonalDataDTO(full_name="Carlos Silva", headline="Dev Python"),
        experiences=[
            ParsedExperienceDTO(
                company_name="Empresa X",
                position_title="Software Engineer",
                start_date="2021-01-01",
                is_current=True,
                description="Desenvolvimento backend.",
                tech_stack=["Python", "PostgreSQL"],
            )
        ],
        educations=[],
        skills=[ParsedSkillDTO(name="Python", category="backend", years_of_experience=4)],
    )

    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER),
        patch("app.api.v1.profile.get_resume_parser_adapter") as mock_get_parser,
    ):
        mock_parser = AsyncMock()
        mock_parser.parse_resume.return_value = mock_dto
        mock_get_parser.return_value = mock_parser

        files = {"file": ("curriculo.pdf", b"%PDF-1.5 valid content", "application/pdf")}
        response = await async_client.post(
            "/api/v1/profile/parse-resume",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["personal_data"]["full_name"] == "Carlos Silva"
        assert len(data["experiences"]) == 1
        assert data["experiences"][0]["company_name"] == "Empresa X"


@pytest.mark.asyncio
async def test_parse_resume_parser_failure_returns_422(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Valida que falhas da engine de extração retornam HTTP 422 tratadas."""
    with (
        patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER),
        patch("app.api.v1.profile.get_resume_parser_adapter") as mock_get_parser,
    ):
        mock_parser = AsyncMock()
        mock_parser.parse_resume.side_effect = ResumeParserError("Modelo indisponível no momento")
        mock_get_parser.return_value = mock_parser

        files = {"file": ("curriculo.pdf", b"%PDF-1.5 content", "application/pdf")}
        response = await async_client.post(
            "/api/v1/profile/parse-resume",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 422
        assert "Modelo indisponível" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_parsed_profile_saves_entities(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Valida a persistência em lote no banco e recuperação posterior no dossiê completo."""
    payload = {
        "personal_data": {
            "full_name": "Roberta Rocha",
            "headline": "Cloud Solutions Architect",
            "phone": "+55 21 98888-7777",
            "location": "Rio de Janeiro, RJ",
            "linkedin_url": "https://linkedin.com/in/robertarocha",
        },
        "experiences": [
            {
                "company_name": "Cloud Enterprise",
                "position_title": "Solutions Architect",
                "location": "Remoto",
                "work_model": "remote",
                "start_date": "2020-03-01",
                "end_date": "2023-08-31",
                "is_current": False,
                "description": "Arquitetura multi-cloud.",
                "bullet_points": ["Liderou migração para GCP"],
                "tech_stack": ["GCP", "Terraform", "Kubernetes"],
                "quantifiable_results": ["Economia de $50k/mês"],
            }
        ],
        "educations": [
            {
                "institution_name": "UFRJ",
                "degree": "Engenharia",
                "field_of_study": "Engenharia de Software",
                "start_date": "2015-01-01",
                "end_date": "2019-12-31",
                "is_current": False,
            }
        ],
        "skills": [
            {
                "name": "Terraform",
                "category": "devops",
                "proficiency_level": "advanced",
                "years_of_experience": 5,
            }
        ],
        "languages": [
            {
                "language_name": "Espanhol",
                "proficiency_level": "advanced",
            }
        ],
        "certifications": [
            {
                "name": "Google Cloud Professional Architect",
                "issuing_organization": "Google Cloud",
                "issue_date": "2022-05-10",
            }
        ],
        "projects": [
            {
                "title": "Open Cloud Infra",
                "description": "Módulos reutilizáveis de Terraform.",
                "technologies": ["HCL", "GCP"],
            }
        ],
    }

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=AUTH_USER):
        # 1. Enviar lote para importação
        res = await async_client.post(
            "/api/v1/profile/import-parsed",
            headers=auth_headers,
            json=payload,
        )
        assert res.status_code == 201
        counts = res.json()
        assert counts["experiences"] == 1
        assert counts["educations"] == 1
        assert counts["skills"] == 1
        assert counts["languages"] == 1
        assert counts["certifications"] == 1
        assert counts["projects"] == 1

        # 2. Consultar dossiê completo para validar persistência
        dossier_res = await async_client.get(
            "/api/v1/profile/full",
            headers=auth_headers,
        )
        assert dossier_res.status_code == 200
        dossier = dossier_res.json()
        assert any(e["company_name"] == "Cloud Enterprise" for e in dossier["experiences"])
        assert any(ed["institution_name"] == "UFRJ" for ed in dossier["educations"])
        assert any(s["name"] == "Terraform" for s in dossier["skills"])
        assert any(lang["language_name"] == "Espanhol" for lang in dossier["languages"])
        assert any(
            c["name"] == "Google Cloud Professional Architect" for c in dossier["certifications"]
        )
        assert any(p["title"] == "Open Cloud Infra" for p in dossier["projects"])
