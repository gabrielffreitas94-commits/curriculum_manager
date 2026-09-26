"""Suíte de testes unitários para o módulo de segurança de arquivos (file_security.py).

Implementa guardrails anti-regressão estritos contra upload de arquivos maliciosos,
disfarçados e exaustão de memória/DoS (CWE-434 / CWE-400 / OWASP A04).
"""

import io
import zipfile
from unittest.mock import patch

import pytest

from app.core.file_security import (
    MAX_RESUME_FILE_SIZE_BYTES,
    MIME_DOCX,
    MIME_PDF,
    PDF_MAGIC_BYTES,
    FileContentMismatchError,
    FileTooLargeError,
    InvalidFileTypeError,
    validate_resume_file,
)


def test_guardrail_reject_empty_file() -> None:
    """Valida rejeição fail-closed quando arquivo de upload possui zero bytes.

    VETOR DE AMEAÇA:
    - CWE-398: Indicador de erro ignorado / processamento de input nulo.
    - Impacto Potencial: Erros de desreferenciamento em bibliotecas de parsing
      e consumo inútil de quotas.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O validador DEVE recusar sumariamente bytes vazios com InvalidFileTypeError.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Um refactor futuro poderia remover a checagem 'if not file_bytes' achando
      redundante com os magic bytes.
    - Sem ela, indexações [0:5] em bytes vazios causariam comportamentos não intencionais.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - A invocação com b'' DEVE levantar InvalidFileTypeError com mensagem sobre arquivo vazio.
    """
    with pytest.raises(InvalidFileTypeError, match="vazio"):
        validate_resume_file(file_bytes=b"", filename="curriculo.pdf")


def test_guardrail_reject_file_exceeding_max_size() -> None:
    """Valida barreira fail-closed contra arquivos que excedem o tamanho máximo (DoS).

    VETOR DE AMEAÇA:
    - CWE-400: Uncontrolled Resource Consumption (Esgotamento de Memória / DoS).
    - Impacto Potencial: Ataque de negação de serviço forçando alocação de RAM no backend.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Rejeitar sumariamente qualquer carga útil que exceda MAX_RESUME_FILE_SIZE_BYTES
      antes de qualquer parsing.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Remover a validação de tamanho antes do envio para a API de IA geraria custos
      exorbitantes e risco de crash da aplicação.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Payload com (MAX_RESUME_FILE_SIZE_BYTES + 1) bytes DEVE levantar FileTooLargeError.
    """
    huge_payload = b"%PDF-" + b"0" * (MAX_RESUME_FILE_SIZE_BYTES)
    with pytest.raises(FileTooLargeError, match="limite máximo"):
        validate_resume_file(file_bytes=huge_payload, filename="huge.pdf")


def test_guardrail_reject_disallowed_extension() -> None:
    """Valida bloqueio estrito contra extensões não suportadas ou perigosas.

    VETOR DE AMEAÇA:
    - CWE-434: Unrestricted Upload of File with Dangerous Type.
    - Impacto Potencial: Upload de scripts (.sh, .exe, .html) visando execução remota ou XSS.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Somente extensões .pdf e .docx são aceitas. Qualquer outra resulta em InvalidFileTypeError.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Permitir extensões arbitrárias confiando apenas no MIME type enviado pelo navegador.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Upload de arquivos com extensões .exe, .sh, .py, .png ou sem extensão DEVE ser rejeitado.
    """
    for bad_name in ["script.sh", "virus.exe", "curriculo.png", "payload.py", "sem_extensao"]:
        with pytest.raises(InvalidFileTypeError, match="não suportada"):
            validate_resume_file(file_bytes=b"%PDF-fake", filename=bad_name)


def test_guardrail_reject_executable_disguised_as_pdf() -> None:
    """Valida inspeção estrita de Magic Bytes contra executáveis renomeados para .pdf.

    VETOR DE AMEAÇA:
    - CWE-434 / OWASP File Upload: Bypassing file upload filters via extension spoofing.
    - Impacto Potencial: Invasor renomeia binário malicioso para .pdf para burlar checagem.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Mesmo com nome .pdf, se bytes não forem '%PDF-', rejeitar com FileContentMismatchError.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Confiar apenas no content-type informado pelo cliente HTTP ou no sufixo do arquivo.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Arquivo renomeado com assinatura PE/MZ DEVE falhar com FileContentMismatchError.
    """
    disguised_executable = b"MZ\x90\x00\x03\x00\x00\x00ThisIsAnExecutableDisguisedAsPdf"
    with pytest.raises(FileContentMismatchError, match="não corresponde a um documento PDF"):
        validate_resume_file(file_bytes=disguised_executable, filename="meu_curriculo.pdf")


def test_guardrail_reject_corrupted_or_fake_docx() -> None:
    """Valida inspeção de Magic Bytes para arquivos com extensão .docx.

    VETOR DE AMEAÇA:
    - CWE-434: Upload de payload adulterado disfarçado de arquivo do Office.
    - Impacto Potencial: Provocar exceções inesperadas em parsers de XML e bibliotecas docx.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Um arquivo .docx DEVE obrigatoriamente iniciar com a assinatura de arquivo ZIP.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Omitir a validação binária de arquivos DOCX achando que apenas PDFs precisam de checagem.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Arquivo de texto puro salvo com nome .docx DEVE falhar com FileContentMismatchError.
    """
    fake_docx = b"Plain text disguised as docx"
    with pytest.raises(FileContentMismatchError, match="não corresponde a um documento Word"):
        validate_resume_file(file_bytes=fake_docx, filename="documento.docx")


def test_validate_resume_file_success_pdf() -> None:
    """Valida sucesso na validação de um arquivo PDF autêntico com magic bytes corretos."""
    valid_pdf_bytes = PDF_MAGIC_BYTES + b"1.4 binary content..."
    mime, ext = validate_resume_file(file_bytes=valid_pdf_bytes, filename="curriculo_joao.PDF")
    assert mime == MIME_PDF
    assert ext == ".pdf"


def test_validate_resume_file_success_docx() -> None:
    """Valida sucesso na validação de um arquivo Word DOCX autêntico com estrutura ZIP válida."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("[Content_Types].xml", b'<?xml version="1.0" encoding="UTF-8"?><Types></Types>')
        zf.writestr(
            "word/document.xml", b'<?xml version="1.0" encoding="UTF-8"?><w:document></w:document>'
        )
    valid_docx_bytes = buf.getvalue()
    mime, ext = validate_resume_file(file_bytes=valid_docx_bytes, filename="curriculo_maria.DOCX")
    assert mime == MIME_DOCX
    assert ext == ".docx"


def test_guardrail_reject_docx_uncompressed_size_limit() -> None:
    """Valida rejeição de arquivos DOCX cujo tamanho descomprimido excede 50MB.

    VETOR DE AMEAÇA:
    - CWE-409: Improper Handling of Highly Compressed Data (Zip Bomb / Decompression Bomb).
    - Impacto Potencial: Exaustão de memória da aplicação e DoS no servidor.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Se a soma dos tamanhos descompactados dos arquivos internos ultrapassar MAX_DOCX_UNCOMPRESSED_SIZE_BYTES,
      lançar FileTooLargeError imediatamente.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Validar apenas o tamanho do payload comprimido sem inspecionar o header de descompressão dos arquivos internos.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - DOCX cujo somatório ultrapasse 50 MB lança FileTooLargeError com mensagem explicativa.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("[Content_Types].xml", b'<?xml version="1.0" encoding="UTF-8"?><Types></Types>')

    mock_info = zipfile.ZipInfo("[Content_Types].xml")
    mock_info.file_size = 55 * 1024 * 1024  # 55MB > 50MB
    with (
        patch("zipfile.ZipFile.infolist", return_value=[mock_info]),
        pytest.raises(FileTooLargeError, match="excede o limite máximo permitido de segurança"),
    ):
        validate_resume_file(file_bytes=buf.getvalue(), filename="huge_docx.docx")
