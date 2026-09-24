"""Testes unitários e guardrails anti-regressão para o Settings do core/config.py."""

import base64
import os

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings

VALID_TEST_SECRET_KEY = "test-secret-key-with-strong-entropy-32-chars!!"


def test_settings_blocks_missing_encryption_key_in_any_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garante que o boot falha imediatamente caso a MASTER_ENCRYPTION_KEY esteja ausente.

    VETOR DE AMEAÇA:
    - CWE-321: Use of Hard-coded Cryptographic Key / CWE-1188: Initialization with Insecure Default.
    - Requisito Estrito: Variáveis de ambiente são obrigatórias em dev, test, staging e prod.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - A inicialização do Settings DEVE abortar com erro de validação do Pydantic
      caso MASTER_ENCRYPTION_KEY não seja fornecida no ambiente.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Instanciação sem MASTER_ENCRYPTION_KEY levanta ValidationError em qualquer ENVIRONMENT.
    """
    monkeypatch.delenv("MASTER_ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="development",
            SECRET_KEY=VALID_TEST_SECRET_KEY,
            _env_file=None,
        )

    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY=VALID_TEST_SECRET_KEY,
            _env_file=None,
        )


def test_settings_blocks_missing_secret_key_in_any_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garante que o boot falha imediatamente caso a SECRET_KEY de sessão esteja ausente.

    VETOR DE AMEAÇA:
    - CWE-321: Use of Hard-coded Cryptographic Key.
    - Sessão Web Forjada: Sem SECRET_KEY estrita e obrigatória, tokens de sessão
      não podem ser emitidos.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - A inicialização do Settings DEVE abortar com ValidationError caso
      SECRET_KEY não seja fornecida.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Instanciação sem SECRET_KEY levanta ValidationError em qualquer ENVIRONMENT.
    """
    monkeypatch.delenv("SECRET_KEY", raising=False)
    valid_key = base64.b64encode(os.urandom(32)).decode("utf-8")
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="development",
            MASTER_ENCRYPTION_KEY=valid_key,
            _env_file=None,
        )


def test_settings_blocks_short_secret_key() -> None:
    """Garante que SECRET_KEY com menos de 32 caracteres seja rejeitada no boot."""
    valid_key = base64.b64encode(os.urandom(32)).decode("utf-8")
    with pytest.raises(ValueError, match="entropia de no mínimo 32 caracteres"):
        Settings(
            MASTER_ENCRYPTION_KEY=valid_key,
            SECRET_KEY="short-secret-key",
            _env_file=None,
        )


def test_settings_accepts_strong_random_key_in_production_and_staging() -> None:
    """Valida que Settings aceita chaves Base64 de 32 bytes criptograficamente fortes em produção.

    VETOR DE AMEAÇA:
    - OWASP A02:2021 (Cryptographic Failures) / Disponibilidade do Serviço (Boot em Produção).
    - Impacto: Chaves válidas geradas via Secret Manager ou CSPRNG devem ser aceitas
      sem falsos positivos.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Aceita chave Base64 de exatamente 32 bytes gerada aleatoriamente em produção e staging.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Se a lógica de comparação do validador comparar tamanhos de string em vez de bytes,
      chaves válidas poderiam ser rejeitadas ou chaves fracas aceitas.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Gera 32 bytes aleatórios via os.urandom e confirma sucesso na inicialização.
    """
    random_bytes = os.urandom(32)
    valid_key_b64 = base64.b64encode(random_bytes).decode("utf-8")

    prod_settings = Settings(
        ENVIRONMENT="production",
        MASTER_ENCRYPTION_KEY=valid_key_b64,
        SECRET_KEY=VALID_TEST_SECRET_KEY,
        _env_file=None,
    )
    assert prod_settings.ENVIRONMENT == "production"
    assert valid_key_b64 == prod_settings.MASTER_ENCRYPTION_KEY

    staging_settings = Settings(
        ENVIRONMENT="staging",
        MASTER_ENCRYPTION_KEY=valid_key_b64,
        SECRET_KEY=VALID_TEST_SECRET_KEY,
        _env_file=None,
    )
    assert staging_settings.ENVIRONMENT == "staging"
    assert valid_key_b64 == staging_settings.MASTER_ENCRYPTION_KEY


def test_settings_blocks_invalid_base64_encryption_key() -> None:
    """Garante que strings que não são Base64 válido sejam rejeitadas no boot.

    VETOR DE AMEAÇA:
    - OWASP A02:2021 (Cryptographic Failures) / CWE-326 (Inadequate Encryption Strength).
    - Impacto: Inicialização com chave corrompida causaria falhas imprevisíveis durante
      a operação em tempo de execução ao invés de fail-fast no boot.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Abortar a inicialização levantando ValueError quando o valor não for Base64 válido.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Deixar a validação para o CryptoService durante requisições HTTP individuais
      transformaria um erro de infraestrutura em erros 500 para usuários finais.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Verifica lançamento estrito de ValueError contendo 'deve ser Base64 de 32 bytes'.
    """
    invalid_b64 = "### NOT_A_VALID_BASE64_STRING ###"
    with pytest.raises(
        ValueError, match="MASTER_ENCRYPTION_KEY inválida: deve ser Base64 de 32 bytes"
    ):
        Settings(
            MASTER_ENCRYPTION_KEY=invalid_b64,
            SECRET_KEY=VALID_TEST_SECRET_KEY,
            _env_file=None,
        )


def test_settings_blocks_short_or_long_encryption_key() -> None:
    """Garante que chaves decodificadas com comprimento diferente de 32 bytes sejam rejeitadas.

    VETOR DE AMEAÇA:
    - OWASP A02:2021 (Cryptographic Failures) / CWE-326 (Inadequate Encryption Strength).
    - Impacto: Uso de chaves curtas (ex: 16 bytes = 128 bits) fragiliza a entropia
      e viola a premissa de AES-256-GCM.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Rejeitar chaves com 16 bytes, 31 bytes ou 33 bytes levantando ValueError.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Se o validador apenas verificar comprimento de string em vez de decodificar bytes,
      paddings anômalos ou chaves decodificadas incorretamente passariam despercebidos.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Verifica que chaves de 16 bytes e 33 bytes decodificadas levantam ValueError no boot.
    """
    short_key = base64.b64encode(b"short_16_bytes!!").decode("utf-8")
    with pytest.raises(ValueError, match="A MASTER_ENCRYPTION_KEY deve conter exatamente 32 bytes"):
        Settings(
            MASTER_ENCRYPTION_KEY=short_key,
            SECRET_KEY=VALID_TEST_SECRET_KEY,
            _env_file=None,
        )

    long_key = base64.b64encode(b"a" * 33).decode("utf-8")
    with pytest.raises(ValueError, match="A MASTER_ENCRYPTION_KEY deve conter exatamente 32 bytes"):
        Settings(
            MASTER_ENCRYPTION_KEY=long_key,
            SECRET_KEY=VALID_TEST_SECRET_KEY,
            _env_file=None,
        )


def test_settings_singleton_properties() -> None:
    """Verifica se a instância singleton padrão do módulo possui os atributos configurados."""
    assert "ThothCVs" in settings.PROJECT_NAME
    assert "http://localhost:3000" in settings.BACKEND_CORS_ORIGINS
    assert settings.STORAGE_PROVIDER == "supabase"
    assert settings.DATABASE_URL.startswith("sqlite")
    assert isinstance(settings.MASTER_ENCRYPTION_KEY, str)


def test_settings_rate_limit_properties() -> None:
    """Verifica se os atributos de Rate Limiting padrão estão configurados."""
    assert settings.RATE_LIMIT_ENABLED is True
    assert settings.RATE_LIMIT_ANALYZE_JOB == "10/minute"
    assert settings.RATE_LIMIT_MATCH_PREVIEW == "10/minute"
    assert settings.RATE_LIMIT_GENERATE == "5/minute"


def test_settings_oauth_properties() -> None:
    """Verifica se os atributos de Google OAuth e Session Key estão configurados."""
    assert hasattr(settings, "GOOGLE_CLIENT_ID")
    assert hasattr(settings, "GOOGLE_CLIENT_SECRET")
    assert "http://localhost:8000/auth/callback/google" in settings.GOOGLE_REDIRECT_URI
    assert isinstance(settings.SECRET_KEY, str)
    assert len(settings.SECRET_KEY) > 0
