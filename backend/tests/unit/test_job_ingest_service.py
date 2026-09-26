"""Testes unitários e guardrails de segurança para o JobIngestService.

Valida a ingestão segura de documentos (.pdf, .docx) e scraping de URLs com
blindagem contra SSRF (CWE-918), DoS por exaustão (CWE-400) e arquivos maliciosos (CWE-434).
"""

import zipfile
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from docx import Document
from fastapi import HTTPException
from pypdf import PdfWriter

from app.core.url_scraper import (
    PayloadTooLargeError,
    ScraperTimeoutError,
    SSRFProtectionError,
    UrlScraperError,
)
from app.services.job_ingest_service import JobIngestService


def _create_minimal_pdf_bytes(text: str) -> bytes:
    """Gera um PDF sintético válido em memória contendo uma página de texto."""
    writer = PdfWriter()
    # Adiciona uma página com dimensões padrão
    writer.add_blank_page(width=300, height=300)
    # Injeta anotação ou texto básico
    buf = BytesIO()
    writer.write(buf)
    # Como PdfWriter add_blank_page não renderiza fontes nativas simples sem reportlab,
    # simulamos o extract_text via patch ou gerando um stream com texto
    return buf.getvalue()


def _create_minimal_docx_bytes(
    paragraphs: list[str], table_data: list[list[str]] | None = None
) -> bytes:
    """Gera um DOCX sintético válido em memória com parágrafos e tabelas."""
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    if table_data:
        table = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
        for r_idx, row in enumerate(table_data):
            for c_idx, val in enumerate(row):
                table.cell(r_idx, c_idx).text = val
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


class TestJobIngestDocument:
    """Testes para extração de texto a partir de arquivos PDF e DOCX."""

    def test_extract_text_from_valid_docx(self) -> None:
        """Valida extração completa de parágrafos e células de tabela em arquivos DOCX."""
        service = JobIngestService()
        docx_bytes = _create_minimal_docx_bytes(
            paragraphs=["Vaga: Engenheiro de Software Sênior", "Requisitos: FastAPI e AWS"],
            table_data=[["Salário", "Benefícios"], ["R$ 20.000", "Plano de Saúde"]],
        )

        extracted = service.extract_text_from_document(docx_bytes, "vaga_tech.docx")
        assert "Engenheiro de Software Sênior" in extracted
        assert "Requisitos: FastAPI e AWS" in extracted
        assert "Salário | Benefícios" in extracted
        assert "R$ 20.000 | Plano de Saúde" in extracted

    def test_extract_text_from_valid_pdf_with_text(self) -> None:
        """Valida extração de texto a partir de arquivo PDF válido."""
        service = JobIngestService()
        pdf_bytes = _create_minimal_pdf_bytes("Job Description")

        with patch("app.services.job_ingest_service.PdfReader") as mock_pdf_reader:
            mock_page = type(
                "MockPage", (), {"extract_text": lambda self: "Vaga Especialista Python Cloud"}
            )()
            mock_reader_inst = type("MockReader", (), {"pages": [mock_page]})()
            mock_pdf_reader.return_value = mock_reader_inst

            extracted = service.extract_text_from_document(pdf_bytes, "anuncio.pdf")
            assert "Vaga Especialista Python Cloud" in extracted

    def test_guardrail_rejects_malicious_executable_renamed_to_pdf(self) -> None:
        """VETOR DE AMEAÇA: CWE-434 (Unrestricted Upload of Dangerous File Type).
        Um atacante renomeia um executável PE (.exe) ou script malicioso para '.pdf'.

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        O serviço deve verificar os magic bytes e rejeitar sumariamente com HTTP 400.

        RISCO DE REGRESSÃO SILENCIOSA:
        Validar apenas a extensão do arquivo permitiria salvar arquivos arbitrários.

        PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
        Magic bytes inválidos devem levantar HTTPException 400.
        """
        service = JobIngestService()
        fake_pdf_bytes = b"MZ\x90\x00\x03\x00\x00\x00MALICIOUS_EXE_CONTENT"

        with pytest.raises(HTTPException) as exc_info:
            service.extract_text_from_document(fake_pdf_bytes, "malware.pdf")
        assert exc_info.value.status_code == 400
        assert "Magic Bytes inválidos" in exc_info.value.detail

    def test_guardrail_rejects_oversized_document(self) -> None:
        """VETOR DE AMEAÇA: CWE-400 (Resource Exhaustion via Gigantic Upload).
        Arquivo com tamanho superior ao limite de 5 MB.

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        Rejeição imediata com HTTP 413 Payload Too Large.
        """
        service = JobIngestService()
        huge_bytes = b"%PDF-" + b"0" * (5 * 1024 * 1024 + 100)

        with pytest.raises(HTTPException) as exc_info:
            service.extract_text_from_document(huge_bytes, "big_job.pdf")
        assert exc_info.value.status_code == 413
        assert "excede o limite máximo permitido de 5 MB" in exc_info.value.detail

    def test_extract_text_empty_document_raises_error(self) -> None:
        """Garante que documentos sem texto extraível levantem HTTP 400."""
        service = JobIngestService()
        docx_empty_bytes = _create_minimal_docx_bytes([])

        with pytest.raises(HTTPException) as exc_info:
            service.extract_text_from_document(docx_empty_bytes, "empty.docx")
        assert exc_info.value.status_code == 400
        assert "não contém texto legível ou extraível" in exc_info.value.detail

    def test_extract_text_corrupted_document_raises_error(self) -> None:
        """Garante tratamento gracioso quando a biblioteca de parsing falha."""
        service = JobIngestService()
        valid_docx = BytesIO()
        with zipfile.ZipFile(valid_docx, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
            zf.writestr("word/document.xml", "<document/>")

        with patch(
            "app.services.job_ingest_service.Document",
            side_effect=Exception("Estrutura corrompida"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                service.extract_text_from_document(valid_docx.getvalue(), "corrupted.docx")
            assert exc_info.value.status_code == 400
            assert "Não foi possível processar o documento enviado" in exc_info.value.detail

    def test_extract_text_security_validation_failure_raises_400(self) -> None:
        """Garante que falhas de validação de segurança de arquivo retornem HTTP 400."""
        service = JobIngestService()
        corrupted_docx = b"PK\x03\x04" + b"\x00" * 50

        with pytest.raises(HTTPException) as exc_info:
            service.extract_text_from_document(corrupted_docx, "corrupted.docx")
        assert exc_info.value.status_code == 400
        assert "O arquivo DOCX não é um arquivo ZIP válido." in exc_info.value.detail


class TestJobIngestUrl:
    """Testes para scraping seguro de vagas a partir de URLs."""

    @pytest.mark.asyncio
    async def test_extract_text_from_url_success(self) -> None:
        """Valida fluxo de sucesso no scraping de URL."""
        service = JobIngestService()
        with patch(
            "app.services.job_ingest_service.safe_fetch_url", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = "Descrição da vaga de Tech Lead no Google."

            text = await service.extract_text_from_url("https://careers.google.com/jobs/123")
            assert "Descrição da vaga de Tech Lead no Google." in text

    @pytest.mark.asyncio
    async def test_guardrail_url_ssrf_blocked_raises_http_400(self) -> None:
        """VETOR DE AMEAÇA: CWE-918 (SSRF via Job Ingestion URL).
        Tentativa de acessar endpoints internos ou metadados de nuvem.

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        Lançamento de HTTPException 400 informando bloqueio de segurança.
        """
        service = JobIngestService()
        with patch(
            "app.services.job_ingest_service.safe_fetch_url", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.side_effect = SSRFProtectionError("IP privado 10.0.0.1 bloqueado.")

            with pytest.raises(HTTPException) as exc_info:
                await service.extract_text_from_url("http://internal-hr.local/job")
            assert exc_info.value.status_code == 400
            assert "Acesso bloqueado por segurança" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_guardrail_url_payload_too_large_raises_http_413(self) -> None:
        """VETOR DE AMEAÇA: CWE-400 (Memory Exhaustion via Giant Webpage).
        URL que retorna stream maior que 2 MB.

        COMPORTAMENTO ESPERADO (FAIL-CLOSED):
        Lançamento de HTTPException 413 Payload Too Large.
        """
        service = JobIngestService()
        with patch(
            "app.services.job_ingest_service.safe_fetch_url", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.side_effect = PayloadTooLargeError("Excedeu 2 MB")

            with pytest.raises(HTTPException) as exc_info:
                await service.extract_text_from_url("https://jobs.example.com/giant")
            assert exc_info.value.status_code == 413
            assert "excede o limite máximo permitido (2 MB)" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_extract_text_from_url_timeout_raises_http_504(self) -> None:
        """Valida que timeout no scraping gere HTTP 504 Gateway Timeout."""
        service = JobIngestService()
        with patch(
            "app.services.job_ingest_service.safe_fetch_url", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.side_effect = ScraperTimeoutError("Timeout após 8s")

            with pytest.raises(HTTPException) as exc_info:
                await service.extract_text_from_url("https://slow.example.com/job")
            assert exc_info.value.status_code == 504
            assert "Tempo limite esgotado" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_extract_text_from_url_general_error_raises_http_400(self) -> None:
        """Valida erro genérico de rede/transporte gerando HTTP 400."""
        service = JobIngestService()
        with patch(
            "app.services.job_ingest_service.safe_fetch_url", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.side_effect = UrlScraperError("DNS resolve failed")

            with pytest.raises(HTTPException) as exc_info:
                await service.extract_text_from_url("https://bad.example.com/job")
            assert exc_info.value.status_code == 400
            assert "Não foi possível obter a vaga" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_extract_text_from_url_empty_text_raises_http_400(self) -> None:
        """Valida página retornando HTML sem nenhum texto visível."""
        service = JobIngestService()
        with patch(
            "app.services.job_ingest_service.safe_fetch_url", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = "   "

            with pytest.raises(HTTPException) as exc_info:
                await service.extract_text_from_url("https://empty.example.com/job")
            assert exc_info.value.status_code == 400
            assert "Nenhum conteúdo textual legível foi encontrado" in exc_info.value.detail
