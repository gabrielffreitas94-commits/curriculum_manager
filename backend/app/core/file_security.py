"""Módulo de validação e segurança para upload de arquivos (AppSec / Defense-in-Depth).

Aplica validação estrita de Magic Bytes, limites de tamanho de payload (CWE-400)
e rejeição fail-closed contra arquivos executáveis disfarçados (CWE-434).
"""

from pathlib import Path


class FileSecurityError(Exception):
    """Exceção base para violações de segurança de arquivos."""


class FileTooLargeError(FileSecurityError):
    """Lançada quando o arquivo excede o limite máximo permitido."""


class InvalidFileTypeError(FileSecurityError):
    """Lançada quando a extensão ou formato não é permitido."""


class FileContentMismatchError(FileSecurityError):
    """Lançada quando os Magic Bytes não correspondem à extensão declarada."""


# Limite máximo padrão: 5 MB
MAX_RESUME_FILE_SIZE_BYTES: int = 5 * 1024 * 1024

# Magic bytes conhecidos
PDF_MAGIC_BYTES: bytes = b"%PDF-"
DOCX_MAGIC_BYTES: bytes = b"PK\x03\x04"

# MIME types aceitos
MIME_PDF: str = "application/pdf"
MIME_DOCX: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

ALLOWED_EXTENSIONS: set[str] = {".pdf", ".docx"}


def validate_resume_file(
    file_bytes: bytes,
    filename: str,
    content_type: str | None = None,
    max_size_bytes: int = MAX_RESUME_FILE_SIZE_BYTES,
) -> tuple[str, str]:
    """Valida estritamente a integridade, extensão e Magic Bytes de um arquivo de currículo.

    Aplica princípio Fail-Closed: se houver qualquer divergência entre a extensão
    declarada e a assinatura binária real, o arquivo é rejeitado sumariamente.

    Args:
        file_bytes: Conteúdo binário bruto do arquivo.
        filename: Nome original do arquivo enviado pelo cliente.
        content_type: MIME type declarado pelo navegador (opcional).
        max_size_bytes: Limite máximo em bytes (default: 5 MB).

    Returns:
        tuple[str, str]: Tupla contendo o MIME type seguro e a extensão normalizada.

    Raises:
        FileTooLargeError: Se o tamanho exceder o limite máximo.
        InvalidFileTypeError: Se a extensão ou arquivo estiver vazio ou não for suportado.
        FileContentMismatchError: Se os Magic Bytes não corresponderem à extensão.
    """
    if not file_bytes:
        raise InvalidFileTypeError("O arquivo enviado está vazio (0 bytes).")

    if len(file_bytes) > max_size_bytes:
        raise FileTooLargeError(
            f"O arquivo excede o limite máximo permitido de {max_size_bytes // (1024 * 1024)} MB."
        )

    clean_filename = Path(filename).name if filename else ""
    ext = Path(clean_filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(
            f"Extensão '{ext or 'desconhecida'}' não suportada. "
            "Envie um arquivo PDF (.pdf) ou Word (.docx)."
        )

    if ext == ".pdf":
        if not file_bytes.startswith(PDF_MAGIC_BYTES):
            raise FileContentMismatchError(
                "O conteúdo do arquivo não corresponde a um documento PDF válido "
                "(Magic Bytes inválidos)."
            )
        return MIME_PDF, ".pdf"

    # ext == ".docx" (garantido pela validação de ALLOWED_EXTENSIONS acima)
    if not file_bytes.startswith(DOCX_MAGIC_BYTES):
        raise FileContentMismatchError(
            "O conteúdo do arquivo não corresponde a um documento Word (.docx) válido "
            "(Magic Bytes inválidos)."
        )
    return MIME_DOCX, ".docx"
