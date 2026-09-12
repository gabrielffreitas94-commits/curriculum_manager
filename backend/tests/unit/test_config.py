"""Testes unitários e guardrails anti-regressão para o Settings do core/config.py."""

import base64
import os

import pytest

from app.core.config import INSECURE_DEFAULT_ENCRYPTION_KEY, Settings, settings


def test_settings_allows_default_key_in_development_or_test() -> None:
    """Garante que a chave padrão hardcoded é permitida apenas em development e test.

    VETOR DE AMEAÇA:
    - CWE-321: Use of Hard-coded Cryptographic Key.
    - Usabilidade local: Desenvolvedores precisam conseguir rodar a aplicação localmente
      e executar a suíte de testes unitários sem configurar segredos manuais complexos.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Em 'development' e 'test', a chave default DEVE ser aceita sem levantar exceção.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Uma alteração no validador que bloqueie 'development' quebraria os testes unitários
      e o onboarding local de novos desenvolvedores.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Instanciação explícita com ENVIRONMENT='development' e ENVIRONMENT='test'
      deve resultar em instância válida com a chave padrão esperada.
    """
    dev_settings = Settings(
        ENVIRONMENT="development",
        MASTER_ENCRYPTION_KEY=INSECURE_DEFAULT_ENCRYPTION_KEY,
        _env_file=None,
    )
    assert dev_settings.ENVIRONMENT == "development"
    assert dev_settings.MASTER_ENCRYPTION_KEY == INSECURE_DEFAULT_ENCRYPTION_KEY

    test_settings = Settings(
        ENVIRONMENT="test",
        MASTER_ENCRYPTION_KEY=INSECURE_DEFAULT_ENCRYPTION_KEY,
        _env_file=None,
    )
    assert test_settings.ENVIRONMENT == "test"
    assert test_settings.MASTER_ENCRYPTION_KEY == INSECURE_DEFAULT_ENCRYPTION_KEY


def test_settings_blocks_insecure_default_key_in_production() -> None:
    """Garante que o uso da MASTER_ENCRYPTION_KEY padrão em produção seja impedido no boot.

    VETOR DE AMEAÇA:
    - OWASP A02:2021 (Cryptographic Failures) / CWE-321 (Use of Hard-coded Cryptographic Key).
    - Impacto: Chaves de API e tokens cifrados com uma chave pública padrão de repositório
      permitem que qualquer pessoa com acesso ao banco decifre todas as credenciais sensíveis.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O Settings DEVE abortar imediatamente o boot da aplicação com ValueError descritivo
      ao detectar a chave padrão quando ENVIRONMENT='production'.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Um desenvolvedor ou agente IA poderia remover esta verificação para facilitar testes
      em contêineres de homologação ou por considerar o validador 'muito restritivo'.
    - Isso causaria exposição crítica de todas as chaves de API cifradas em produção.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Verifica o lançamento estrito de ValueError com a mensagem contendo
      'CONFIGURAÇÃO INSEGURA: O uso da MASTER_ENCRYPTION_KEY padrão de desenvolvimento é proibido'.
    """
    with pytest.raises(
        ValueError, match="CONFIGURAÇÃO INSEGURA: O uso da MASTER_ENCRYPTION_KEY padrão"
    ):
        Settings(
            ENVIRONMENT="production",
            MASTER_ENCRYPTION_KEY=INSECURE_DEFAULT_ENCRYPTION_KEY,
            _env_file=None,
        )


def test_settings_blocks_insecure_default_key_in_staging() -> None:
    """Garante que o uso da MASTER_ENCRYPTION_KEY padrão em staging seja impedido no boot.

    VETOR DE AMEAÇA:
    - OWASP A02:2021 (Cryptographic Failures) / CWE-321 (Use of Hard-coded Cryptographic Key).
    - Impacto: Ambientes de staging frequentemente utilizam espelhos de bancos ou segredos
      reais; usar a chave default deixaria dados expostos.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O Settings DEVE abortar o boot com ValueError descritivo quando ENVIRONMENT='staging'.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Relaxar o validador apenas para staging criaria uma disparidade de ambiente e
      permitiria que falhas de configuração vazassem até a borda de produção.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Verifica o lançamento estrito de ValueError ao instanciar Settings com ENVIRONMENT='staging'
      e a chave padrão.
    """
    with pytest.raises(
        ValueError, match="CONFIGURAÇÃO INSEGURA: O uso da MASTER_ENCRYPTION_KEY padrão"
    ):
        Settings(
            ENVIRONMENT="staging",
            MASTER_ENCRYPTION_KEY=INSECURE_DEFAULT_ENCRYPTION_KEY,
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
        _env_file=None,
    )
    assert prod_settings.ENVIRONMENT == "production"
    assert valid_key_b64 == prod_settings.MASTER_ENCRYPTION_KEY

    staging_settings = Settings(
        ENVIRONMENT="staging",
        MASTER_ENCRYPTION_KEY=valid_key_b64,
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
            _env_file=None,
        )

    long_key = base64.b64encode(b"a" * 33).decode("utf-8")
    with pytest.raises(ValueError, match="A MASTER_ENCRYPTION_KEY deve conter exatamente 32 bytes"):
        Settings(
            MASTER_ENCRYPTION_KEY=long_key,
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
