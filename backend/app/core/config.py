"""Módulo de configuração central do ThothCVs AI Backend.

Utiliza Pydantic Settings para carregar e validar variáveis de ambiente
com suporte a arquivos .env locais e injeção em produção no Google Cloud Run.
"""

from pydantic import Field
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
    MASTER_ENCRYPTION_KEY: str = "c2VjcmV0LWtleS1mb3ItZGV2ZWxvcG1lbnQtcHVycG9zZXM="
    STORAGE_PROVIDER: str = "supabase"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
