"""Adaptador para o Google Gemini API via SDK google-genai (Hexagonal Architecture).

Implementa a porta AIPort com suporte a Structured Outputs estritos,
BYOK (Bring Your Own Key) e injeção do contexto factual do candidato.
"""

import json
from typing import Any

from google import genai
from google.genai import types

from app.ports.ai_port import (
    AIError,
    AIPort,
    FullGeneratedResumePayload,
    GenerationError,
    JobAnalysisResult,
    MissingApiKeyError,
)


class GeminiAIAdapter(AIPort):
    """Implementação concreta de AIPort consumindo a API oficial do Google Gemini.

    Attributes:
        _api_key: Chave de API do usuário (BYOK) ou chave mestre do ambiente.
        _client: Instância do cliente Google GenAI SDK.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Inicializa o adaptador configurando o cliente GenAI.

        Args:
            api_key: Chave de API do Google Gemini (BYOK) decifrada do banco.
        """
        self._api_key = api_key.strip() if api_key else None
        self._client: genai.Client | None = None

        if self._api_key:
            self._client = genai.Client(api_key=self._api_key)

    def _require_client(self) -> genai.Client:
        """Valida se a chave de API está presente e retorna o cliente GenAI.

        Returns:
            genai.Client: Instância do cliente conectada.

        Raises:
            MissingApiKeyError: Se a chave do Gemini não estiver configurada.
        """
        if not self._api_key or not self._client:
            raise MissingApiKeyError(
                "Chave de API do Gemini não configurada. "
                "Cadastre sua chave pessoal (BYOK) nas configurações da conta."
            )
        return self._client

    async def analyze_job(self, job_description: str) -> JobAnalysisResult:
        """Analisa semanticamente a oportunidade utilizando o gemini-1.5-flash.

        Args:
            job_description: Texto integral da descrição da vaga.

        Returns:
            JobAnalysisResult: Requisitos mandatórios, desejáveis e termos ATS.

        Raises:
            MissingApiKeyError: Caso a chave da API esteja ausente.
            AIError: Em caso de erro na comunicação com a API.
        """
        client = self._require_client()

        prompt = (
            "Você é um especialista em recrutamento técnico e análise ATS. "
            "Analise detalhadamente o anúncio de vaga abaixo e extraia com precisão:\n"
            "1. Título do cargo e senioridade pretendida.\n"
            "2. Requisitos mandatórios inegociáveis.\n"
            "3. Requisitos desejáveis e diferenciais competitivos.\n"
            "4. Palavras-chave fundamentais para os filtros de triagem ATS.\n\n"
            f"--- ANÚNCIO DA VAGA ---\n{job_description}\n"
        )

        try:
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=JobAnalysisResult,
                    temperature=0.2,
                ),
            )
            if not response.text:
                raise GenerationError("Gemini retornou uma resposta vazia para a análise de vaga.")

            data = json.loads(response.text)
            return JobAnalysisResult(**data)
        except AIError:
            raise
        except Exception as exc:
            raise AIError(f"Falha na análise semântica da vaga com Gemini: {exc}") from exc

    async def generate_resume(
        self,
        job_description: str,
        user_dossier: dict[str, Any],
        prompt_skill_instructions: str,
        language: str = "pt-BR",
    ) -> FullGeneratedResumePayload:
        """Gera um currículo adaptado via Structured Outputs respeitando os fatos do usuário.

        Args:
            job_description: Anúncio da vaga de emprego.
            user_dossier: Fatos cadastrados no banco relacional (Ground Truth).
            prompt_skill_instructions: Diretrizes do template de persona escolhido.
            language: Idioma de destino da redação ('pt-BR', 'en-US', etc.).

        Returns:
            FullGeneratedResumePayload: Currículo estruturado e análise de aderência.

        Raises:
            MissingApiKeyError: Se a API key do Gemini estiver ausente.
            GenerationError: Se a geração violar o schema estruturado.
        """
        client = self._require_client()

        system_instruction = (
            "Você é ThothCVs AI, um motor especializado em sintetizar currículos de alto impacto "
            "com conformidade e veracidade absoluta (ZERO ALUCINAÇÃO).\n"
            f"Diretrizes de Tom e Estilo:\n{prompt_skill_instructions}\n\n"
            "REGRAS INEGOCIÁVEIS DE VERACIDADE (ANTI-ALUCINAÇÃO):\n"
            "1. Você SÓ PODE incluir empresas, cargos, graduações e tecnologias que existam "
            "explicitamente no DOSSIÊ DO USUÁRIO.\n"
            "2. É expressamente PROIBIDO inventar empresas, certificações ou números de impacto.\n"
            "3. Se a vaga exigir algo que o candidato não possui, classifique o requisito "
            "como 'missing' na matriz de match e NÃO invente a competência no currículo.\n"
            f"4. O idioma final de redação de todo o documento deve ser estritamente: {language}.\n"
            "5. O preenchimento do campo 'provenance_map' é OBRIGATÓRIO para todas as competências "
            "e tecnologias, mapeando cada termo para o termo factual do DOSSIÊ DO USUÁRIO.\n"
        )

        dossier_json = json.dumps(user_dossier, ensure_ascii=False)
        user_content_prompt = (
            f"--- REQUISITOS DA VAGA ---\n{job_description}\n\n"
            f"--- FATOS REAIS DO CANDIDATO (GROUND TRUTH) ---\n{dossier_json}\n\n"
            "Sintetize o currículo estruturado completo evidenciando as maiores forças do "
            "candidato para esta oportunidade específica."
        )

        try:
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=user_content_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=FullGeneratedResumePayload,
                    temperature=0.3,
                ),
            )
            if not response.text:
                raise GenerationError("Gemini retornou conteúdo vazio na geração do currículo.")

            payload_data = json.loads(response.text)
            return FullGeneratedResumePayload(**payload_data)
        except AIError:
            raise
        except Exception as exc:
            raise GenerationError(f"Falha na síntese estruturada do currículo: {exc}") from exc
