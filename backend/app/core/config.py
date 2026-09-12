"""Módulo de configuração central do ThothCVs AI Backend.

Utiliza Pydantic Settings para carregar e validar variáveis de ambiente
com suporte a arquivos .env locais e injeção em produção no Google Cloud Run.
"""

import base64
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_ENCRYPTION_KEY: str = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


class Settings(BaseSettings):
    """Configurações gerais da aplicação validadas em tempo de inicialização.

    Attributes:
        PROJECT_NAME: Nome oficial do projeto exibido na documentação Swagger.
        VERSION: Versão semântica atual do software.
        API_V1_STR: Prefixo canônico para todas as rotas da versão 1 da API.
        ENVIRONMENT: Identificador do ambiente ('development', 'staging', 'production').
        DEBUG: Flag de depuração ativando logs verbosos.
        BACKEND_CORS_ORIGINS: Lista de origens permitidas para requisições CORS.
        DATABASE_URL: String de conexão assíncrona com o PostgreSQL.
        MASTER_ENCRYPTION_KEY: Chave de 32 bytes em base64 para cifragem AES-GCM-256.
        STORAGE_PROVIDER: Provedor de storage ativo ('supabase' ou 'gcs').
    """

    PROJECT_NAME: str = "ThothCVs AI Backend"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    BACKEND_CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"]
    )

    DATABASE_URL: str = "sqlite+aiosqlite:///./thothcvs_dev.db"
    MASTER_ENCRYPTION_KEY: str = INSECURE_DEFAULT_ENCRYPTION_KEY
    STORAGE_PROVIDER: str = "supabase"

    # Configurações de Rate Limiting (SlowAPI) contra DoS e esgotamento de quota de IA
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_ANALYZE_JOB: str = "10/minute"
    RATE_LIMIT_MATCH_PREVIEW: str = "10/minute"
    RATE_LIMIT_GENERATE: str = "5/minute"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_master_encryption_key(self) -> Self:
        """Garante a integridade e segurança da MASTER_ENCRYPTION_KEY.

        Valida que a chave é uma string Base64 decodificável em exatamente 32 bytes (256 bits).
        Em ambientes 'production' ou 'staging', impede terminantemente o uso da chave padrão
        hardcoded de desenvolvimento para evitar falhas criptográficas graves.
        """
        try:
            raw_key = base64.b64decode(self.MASTER_ENCRYPTION_KEY, validate=True)
            if len(raw_key) != 32:
                raise ValueError("A MASTER_ENCRYPTION_KEY deve conter exatamente 32 bytes.")
        except Exception as exc:
            raise ValueError(
                f"MASTER_ENCRYPTION_KEY inválida: deve ser Base64 de 32 bytes. Erro: {exc}"
            ) from exc

        if (
            self.ENVIRONMENT in ("production", "staging")
            and self.MASTER_ENCRYPTION_KEY == INSECURE_DEFAULT_ENCRYPTION_KEY
        ):
            raise ValueError(
                "CONFIGURAÇÃO INSEGURA: O uso da MASTER_ENCRYPTION_KEY padrão de "
                "desenvolvimento é proibido em ambientes de produção e staging. "
                "Gere uma chave criptográfica forte de 32 bytes (AES-GCM-256) "
                "via Secret Manager."
            )

        return self


settings = Settings()
