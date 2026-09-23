"""Módulo de configuração central do ThothCVs AI Backend.

Utiliza Pydantic Settings para carregar e validar variáveis de ambiente
com suporte a arquivos .env locais e injeção em produção no Google Cloud Run.
"""

import base64
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        MASTER_ENCRYPTION_KEY: Chave de 32 bytes em base64 para cifragem AES-GCM-256 (obrigatória).
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
    MASTER_ENCRYPTION_KEY: str
    STORAGE_PROVIDER: str = "supabase"

    # Configurações de Autenticação OAuth 2.0 e Sessão Web
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/callback/google"
    SECRET_KEY: str

    # Configurações de Rate Limiting (SlowAPI) contra DoS e esgotamento de quota de IA
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_ANALYZE_JOB: str = "10/minute"
    RATE_LIMIT_MATCH_PREVIEW: str = "10/minute"
    RATE_LIMIT_GENERATE: str = "5/minute"

    # Configurações de Cabeçalhos de Segurança HTTP (OWASP A05:2021)
    SECURITY_HEADERS_ENABLED: bool = True
    HSTS_MAX_AGE_SECONDS: int = 31536000
    HSTS_INCLUDE_SUBDOMAINS: bool = True
    HSTS_PRELOAD: bool = False

    # Configurações de Observabilidade e Logging Estruturado (OTel/GCP)
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" (Google Cloud Logging) ou "console" (dev)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_master_encryption_key(self) -> Self:
        """Garante a integridade e segurança da MASTER_ENCRYPTION_KEY em todos os ambientes.

        Valida que a chave é uma string Base64 decodificável em exatamente 32 bytes (256 bits).
        """
        try:
            raw_key = base64.b64decode(self.MASTER_ENCRYPTION_KEY, validate=True)
            if len(raw_key) != 32:
                raise ValueError("A MASTER_ENCRYPTION_KEY deve conter exatamente 32 bytes.")
        except Exception as exc:
            raise ValueError(
                f"MASTER_ENCRYPTION_KEY inválida: deve ser Base64 de 32 bytes. Erro: {exc}"
            ) from exc

        return self

    @model_validator(mode="after")
    def validate_secret_key(self) -> Self:
        """Garante entropia e tamanho mínimo para a SECRET_KEY de sessão em todos os ambientes."""
        if not self.SECRET_KEY or len(self.SECRET_KEY.strip()) < 32:
            raise ValueError(
                "A SECRET_KEY deve ser uma string com entropia de no mínimo 32 caracteres."
            )
        return self


settings = Settings()
