"""Adaptador concreto para extração e parsing de currículos via Google Gemini API.

Implementa a porta ResumeParserPort utilizando o SDK google-genai,
com Structured Outputs e garantia algorítmica de zero alucinação.
"""

import contextlib
import time
from io import BytesIO
from typing import Any

from docx import Document
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.logging import get_logger
from app.ports.resume_parser_port import (
    CorruptedFileError,
    ParsedProfileDTO,
    ParserModelUnavailableError,
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
    "citado.\n"
    "6. Descrições e Realizações das Experiências: Para cada experiência profissional, "
    "extraia integralmente o resumo contextual ou narrativa das responsabilidades no campo 'description', "
    "e cada uma das realizações, projetos ou itens detalhados no campo 'bullet_points', "
    "preservando fielmente o texto original do currículo sem suprimir detalhes.\n"
    "7. Projetos e Iniciativas de Destaque: Para cada projeto presente no currículo, "
    "extraia o título no campo 'title' e todo o detalhamento textual de escopo, objetivos, "
    "arquitetura e desafios no campo 'description', PRESERVANDO INTEGRALMENTE o texto original "
    "sem resumir, sintetizar ou abreviar. Se houver itens, tópicos ou realizações específicas "
    "dentro do projeto, extraia-os integralmente em 'bullet_points', o papel exercido em 'role', "
    "e todas as tecnologias e ferramentas utilizadas em 'technologies'."
)


class GeminiResumeParserAdapter(ResumeParserPort):
    """Implementa a extração de currículos consumindo o modelo multimodal do Gemini.

    Attributes:
        _api_key: Chave do Gemini fornecida (BYOK ou plataforma).
        _client: Instância do cliente Google GenAI.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        thinking_level: str | None = None,
    ) -> None:
        """Inicializa o adaptador configurando o cliente GenAI e parâmetros de modelo.

        Args:
            api_key: Chave de API do Google Gemini.
            model: Identificador do modelo (ex: 'gemini-2.5-flash', 'gemini-3.8-flash').
            thinking_level: Nível de esforço de raciocínio ('low', 'medium', 'high').
        """
        self._api_key = api_key.strip() if api_key else None
        self._model = model.strip() if model else settings.DEFAULT_GEMINI_MODEL
        self._thinking_level = (
            thinking_level.strip().lower()
            if thinking_level
            else settings.DEFAULT_GEMINI_THINKING_LEVEL
        )
        self._client: genai.Client | None = None
        if self._api_key:
            self._client = genai.Client(api_key=self._api_key)

    def _require_client(self) -> genai.Client:
        """Valida se a chave de API está presente e retorna o cliente GenAI."""
        if not self._api_key or not self._client:
            raise ResumeParserError(
                "Chave de API do Gemini não configurada (100% BYOK). "
                "Configure sua chave pessoal em Configurações antes de importar currículos."
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

            config_kwargs: dict[str, Any] = {
                "system_instruction": ZERO_HALLUCINATION_SYSTEM_INSTRUCTION,
                "response_mime_type": "application/json",
                "response_schema": ParsedProfileDTO,
            }
            if not self._model.startswith("gemini-3"):
                config_kwargs["temperature"] = 0.0

            if self._thinking_level in ("low", "medium", "high"):
                with contextlib.suppress(Exception):
                    config_kwargs["thinking_config"] = types.ThinkingConfig(
                        thinking_level=self._thinking_level
                    )

            current_cfg = dict(config_kwargs)
            if self._model.startswith("gemini-3"):
                current_cfg.pop("temperature", None)

            try:
                response = client.models.generate_content(
                    model=self._model,
                    contents=user_content,  # type: ignore[arg-type]
                    config=types.GenerateContentConfig(**current_cfg),
                )
            except Exception as exc:
                err_str = str(exc).lower()
                if any(term in err_str for term in ("503", "unavailable", "high demand")):
                    raise ParserModelUnavailableError(
                        f"Esse modelo ({self._model}) está temporariamente indisponível. "
                        "Tente novamente em alguns minutos ou selecione outro modelo em Configurações.",
                        model=self._model,
                    ) from exc
                if any(
                    term in err_str for term in ("429", "rate limit", "resource exhausted", "quota")
                ):
                    raise ParserModelUnavailableError(
                        f"Esse modelo ({self._model}) atingiu o limite temporário de uso. "
                        "Tente novamente em alguns minutos ou selecione outro modelo em Configurações.",
                        model=self._model,
                    ) from exc
                if any(
                    term in err_str
                    for term in ("404", "not_found", "no longer available", "deprecated")
                ):
                    raise ParserModelUnavailableError(
                        f"Esse modelo ({self._model}) não está mais disponível. "
                        "Por favor, selecione outro modelo atualizado em Configurações.",
                        model=self._model,
                    ) from exc
                raise ParsingExecutionError(
                    f"Falha ao extrair dados do currículo via IA: {exc}"
                ) from exc

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            if not response or not response.text:
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
                "Falha ao extrair dados do currículo via IA. Tente novamente mais tarde."
            ) from exc
