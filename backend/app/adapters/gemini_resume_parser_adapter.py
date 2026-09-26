"""Adaptador concreto para extração e parsing de currículos via Google Gemini API.

Implementa a porta ResumeParserPort utilizando o SDK google-genai,
com Structured Outputs e garantia algorítmica de zero alucinação.
"""

import time
from io import BytesIO

from docx import Document
from google import genai
from google.genai import types

from app.core.logging import get_logger
from app.ports.resume_parser_port import (
    CorruptedFileError,
    ParsedProfileDTO,
    ParsingExecutionError,
    ResumeParserError,
    ResumeParserPort,
)

logger = get_logger(__name__)

ZERO_HALLUCINATION_SYSTEM_INSTRUCTION: str = (
    "Você é um analisador e extrator de alta precisão e fidelidade factual "
    "(Zero-Hallucination Resume Parser) do ThothCVs AI. Sua missão é converter o currículo "
    "fornecido ESTRITAMENTE na estrutura JSON solicitada.\n\n"
    "REGRAS INVIOLÁVEIS:\n"
    "1. ZERO ALUCINAÇÃO: Extraia APENAS o que estiver explicitamente escrito no documento. "
    "NUNCA invente empresas, cargos, datas, métricas, tecnologias, projetos, competências "
    "ou links.\n"
    "2. Se uma informação não estiver presente no documento ou for ambígua, deixe o campo "
    "como nulo (None) ou lista vazia ([]). Jamais deduza ou infira experiências não "
    "declaradas.\n"
    "3. Padronização de Datas: Converta datas para o formato ISO 'YYYY-MM-DD' ou 'YYYY-MM'. "
    "Se apenas o ano for mencionado (ex: '2021'), use '2021-01-01'. Se a experiência for "
    "atual (ex: 'Presente', 'Atual'), marque 'is_current=True' e 'end_date=None'.\n"
    "4. Classificação de Competências: Mapeie as habilidades encontradas em categorias "
    "claras: 'backend', 'frontend', 'cloud', 'devops', 'database', 'architecture', "
    "'methodology', 'soft_skills'.\n"
    "5. Formato de Trabalho: Inferir 'remote', 'hybrid' ou 'on-site' apenas se explicitamente "
    "citado."
)


class GeminiResumeParserAdapter(ResumeParserPort):
    """Implementa a extração de currículos consumindo o modelo multimodal do Gemini.

    Attributes:
        _api_key: Chave do Gemini fornecida (BYOK ou plataforma).
        _client: Instância do cliente Google GenAI.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Inicializa o adaptador configurando o cliente GenAI.

        Args:
            api_key: Chave de API do Google Gemini.
        """
        self._api_key = api_key.strip() if api_key else None
        self._client: genai.Client | None = None
        if self._api_key:
            self._client = genai.Client(api_key=self._api_key)

    def _require_client(self) -> genai.Client:
        """Valida se a chave de API está presente e retorna o cliente GenAI."""
        if not self._api_key or not self._client:
            raise ResumeParserError(
                "Chave de API do Gemini não configurada. "
                "Configure sua chave antes de importar currículos."
            )
        return self._client

    def _extract_docx_text(self, file_bytes: bytes) -> str:
        """Extrai parágrafos e tabelas de um documento DOCX em texto estruturado."""
        try:
            doc = Document(BytesIO(file_bytes))
            chunks: list[str] = []
            for paragraph in doc.paragraphs:
                text = paragraph.text.strip()
                if text:
                    chunks.append(text)
            for table in doc.tables:
                for row in table.rows:
                    row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_cells:
                        chunks.append(" | ".join(row_cells))
            extracted_text = "\n".join(chunks)
            if not extracted_text.strip():
                raise CorruptedFileError("O documento DOCX não contém texto extraível.")
            return extracted_text
        except CorruptedFileError:
            raise
        except Exception as exc:
            logger.error("docx_text_extraction_failed", error=str(exc), exc_info=True)
            raise CorruptedFileError(f"Falha ao ler estrutura do arquivo DOCX: {exc}") from exc

    async def parse_resume(
        self,
        file_bytes: bytes,
        mime_type: str,
        filename: str,
    ) -> ParsedProfileDTO:
        """Extrai os dados estruturados do currículo aplicando Structured Outputs.

        Args:
            file_bytes: Conteúdo binário validado do arquivo.
            mime_type: Tipo MIME ('application/pdf' ou 'application/vnd...').
            filename: Nome original do arquivo.

        Returns:
            ParsedProfileDTO: Entidades factuais extraídas do documento.

        Raises:
            ResumeParserError: Se a chave estiver ausente.
            CorruptedFileError: Se o arquivo estiver ilegível.
            ParsingExecutionError: Se o Gemini retornar erro ou formato inválido.
        """
        client = self._require_client()
        start_time = time.perf_counter()

        logger.info(
            "resume_parsing_initiated",
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_bytes),
        )

        try:
            user_content: list[str | types.Part]
            if mime_type == "application/pdf":
                file_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
                user_content = [
                    file_part,
                    "Extraia todos os dados factuais deste currículo em PDF "
                    "rigorosamente no esquema JSON solicitado.",
                ]
            else:
                docx_text = self._extract_docx_text(file_bytes)
                user_content = [
                    f"Texto extraído do currículo Word (.docx):\n\n{docx_text}\n\n"
                    "Extraia todos os dados factuais deste currículo "
                    "rigorosamente no esquema JSON solicitado."
                ]

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_content,  # type: ignore[arg-type]
                config=types.GenerateContentConfig(
                    system_instruction=ZERO_HALLUCINATION_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=ParsedProfileDTO,
                    temperature=0.0,
                ),
            )

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            if not response.text:
                raise ParsingExecutionError("O modelo de IA retornou uma resposta vazia.")

            parsed_dto = ParsedProfileDTO.model_validate_json(response.text)

            logger.info(
                "resume_parsing_completed",
                filename=filename,
                duration_ms=duration_ms,
                experiences_count=len(parsed_dto.experiences),
                educations_count=len(parsed_dto.educations),
                skills_count=len(parsed_dto.skills),
            )
            return parsed_dto

        except (ResumeParserError, CorruptedFileError):
            raise
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "resume_parsing_failed",
                filename=filename,
                duration_ms=duration_ms,
                error=str(exc),
                exc_info=True,
            )
            raise ParsingExecutionError(
                f"Falha ao extrair dados do currículo via IA: {exc}"
            ) from exc
