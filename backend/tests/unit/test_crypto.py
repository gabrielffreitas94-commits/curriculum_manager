"""Testes unitários para o serviço de criptografia simétrica AES-GCM-256."""

import pytest

from app.core.crypto import CryptoService, DecryptionError


def test_encryption_and_decryption_success() -> None:
    """
    VETOR DE AMEAÇA: CWE-327 (Use of a Broken or Risky Cryptographic Algorithm) & CWE-311 (Missing Encryption of Sensitive Data).
    Armazenamento de segredos críticos (chaves de API do Google Gemini) em texto plano ou com cifras
    inseguras sem integridade autenticada, expondo credenciais de IA em repouso no banco.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    O serviço DEVE criptografar o texto plano utilizando AES-256-GCM com nonce criptográfico único
    gerando ciphertext indistinguível, restaurando o texto original estritamente com a mesma chave mestra.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Um desenvolvedor ou IA pode tentar substituir AES-GCM por uma codificação simples (como Base64)
    ou modo ECB para contornar problemas de gerenciamento de IV, vazando segredos.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    O payload cifrado difere do texto original, possui expansão de overhead (nonce + tag)
    e restaura exatamente a chave secreta original após decifragem.
    """
    # Chave mestra válida de 32 bytes codificada em Base64 (256 bits)
    master_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    service = CryptoService(master_key_base64=master_key)

    secret_text = "AIzaSySecretGeminiApiKey_123456789"
    encrypted_payload = service.encrypt(secret_text)

    # O texto cifrado gerado não pode ser igual ao original
    assert encrypted_payload != secret_text
    assert len(encrypted_payload) > len(secret_text)

    # Decifragem com a mesma chave mestra deve restaurar exatamente o texto
    decrypted_text = service.decrypt(encrypted_payload)
    assert decrypted_text == secret_text


def test_tampered_ciphertext_detection() -> None:
    """Garante que qualquer adulteração no texto cifrado ou tag de autenticação falhe.

    VETOR DE AMEAÇA:
    - OWASP A02:2021 (Cryptographic Failures) / CWE-353 (Missing Support for Integrity Check).
    - Impacto: Modificação maliciosa de dados criptografados em repouso (chaves API ou tokens).

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O algoritmo AES-256-GCM DEVE validar a tag de autenticação e rejeitar payloads adulterados.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Migrar de AES-GCM (cifragem autenticada) para modos não autenticados (ex: AES-CBC sem HMAC)
      permitiria ataques de bit-flipping e padding oracle sem detecção de integridade.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Modifica propositalmente os bytes do ciphertext e assere lançamento de DecryptionError.
    """
    master_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    service = CryptoService(master_key_base64=master_key)

    secret_text = "AIzaSySuperSecretKey"
    encrypted = service.encrypt(secret_text)

    # Altera propositalmente os últimos caracteres do ciphertext Base64
    tampered = encrypted[:-4] + "AAAA"

    with pytest.raises(DecryptionError, match="Falha de autenticação ou payload corrompido"):
        service.decrypt(tampered)


def test_wrong_key_decryption_failure() -> None:
    """Garante que tentar decifrar com uma chave mestra diferente levante DecryptionError.

    VETOR DE AMEAÇA:
    - OWASP A02:2021 (Cryptographic Failures) / CWE-327.
    - Impacto: Tentativa de descriptografia cruzada ou uso de chaves não autorizadas.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Qualquer chave diferente da utilizada na cifragem DEVE falhar imediatamente.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Erros no tratamento de exceções de decifragem que retornem strings vazias ou nulas
      em vez de levantar exceção de domínio permitiriam estado inconsistente na aplicação.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Cifra com service_a e assere que service_b (chave diferente) levanta DecryptionError.
    """
    key_a = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    key_b = "YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODk="

    service_a = CryptoService(master_key_base64=key_a)
    service_b = CryptoService(master_key_base64=key_b)

    encrypted = service_a.encrypt("MySecretPayload")

    with pytest.raises(DecryptionError):
        service_b.decrypt(encrypted)


def test_invalid_key_length_raises_value_error() -> None:
    """Garante que chaves mestras com tamanho diferente de 32 bytes sejam rejeitadas."""
    # Chave com apenas 10 bytes em Base64
    short_key = "YWJjZGVmZ2hpag=="
    with pytest.raises(ValueError, match="A chave mestra deve conter exatamente 32 bytes"):
        CryptoService(master_key_base64=short_key)


def test_associated_data_encryption_and_decryption_success() -> None:
    """Garante que cifragem e decifragem com o mesmo associated_data (tenant) funcione."""
    master_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    service = CryptoService(master_key_base64=master_key)

    secret_text = "AIzaSyTenantBoundApiKey_987654321"
    tenant_aad = b"tenant-user-uuid-12345"

    encrypted = service.encrypt(secret_text, associated_data=tenant_aad)
    assert encrypted != secret_text

    decrypted = service.decrypt(encrypted, associated_data=tenant_aad)
    assert decrypted == secret_text


def test_associated_data_mismatch_fails_authentication() -> None:
    """
    VETOR DE AMEAÇA: CWE-284 (Improper Access Control) & CWE-327 (Cryptographic Issues).
    Invasor autenticado (Bob) tenta decifrar a chave de API de outro tenant (Alice) reaproveitando
    o ciphertext no seu próprio contexto de tenant (Cross-Tenant AEAD Tampering).

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    O algoritmo AES-GCM DEVE validar o contexto de dados associados (AAD) e lançar DecryptionError
    imediatamente se o tenant fornecido na decifragem for diferente do tenant utilizado na cifragem.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Remover o parâmetro 'associated_data' da chamada de decifragem tornaria os dados cifrados
    intercambiáveis e decifráveis entre diferentes tenants que compartilham a mesma base.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    A tentativa de decifrar payload de Alice com o tenant_b de Bob levanta DecryptionError incondicional.
    """
    master_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    service = CryptoService(master_key_base64=master_key)

    secret_text = "AIzaSySecretApiKey"
    tenant_a = b"tenant-user-alice"
    tenant_b = b"tenant-user-bob"

    encrypted_for_alice = service.encrypt(secret_text, associated_data=tenant_a)

    # Bob tenta decifrar os dados da Alice usando seu próprio tenant context
    with pytest.raises(DecryptionError, match="Falha de autenticação ou payload corrompido"):
        service.decrypt(encrypted_for_alice, associated_data=tenant_b)


def test_associated_data_omitted_fails_when_encrypted_with_aad() -> None:
    """
    VETOR DE AMEAÇA: CWE-353 (Missing Support for Integrity Check) / CWE-284.
    Tentativa de decifrar credencial omitindo o contexto AAD (passando associated_data=None)
    para tentar contornar a validação de posse do tenant.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    Se o payload foi cifrado com AAD, a ausência de AAD na decifragem DEVE falhar fail-closed com DecryptionError.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    Tratar AAD como valor default nulo opcional sem validar que payloads cifrados com AAD
    exigem correspondência exata anularia o isolamento criptográfico do tenant.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    Decifrar com 'associated_data=None' payload protegido por AAD levanta DecryptionError.
    """
    master_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    service = CryptoService(master_key_base64=master_key)

    secret = "TopSecret"
    tenant_aad = b"tenant-secure"

    encrypted = service.encrypt(secret, associated_data=tenant_aad)

    with pytest.raises(DecryptionError, match="Falha de autenticação ou payload corrompido"):
        service.decrypt(encrypted, associated_data=None)


def test_invalid_base64_master_key_raises_value_error() -> None:
    """Garante que fornecer uma chave mestre com Base64 inválido lance ValueError."""
    invalid_b64 = "### Not A Valid Base64 String ###"
    with pytest.raises(ValueError, match="não é um Base64 válido"):
        CryptoService(master_key_base64=invalid_b64)


def test_decrypt_invalid_base64_payload_raises_decryption_error() -> None:
    """Garante que tentar decifrar uma string que não é Base64 lance DecryptionError."""
    master_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    service = CryptoService(master_key_base64=master_key)

    with pytest.raises(DecryptionError, match="codificação Base64 inválida"):
        service.decrypt("abcde")


def test_decrypt_payload_too_short_raises_decryption_error() -> None:
    """Garante que payload menor ou igual aos 12 bytes do nonce lance DecryptionError."""
    import base64

    master_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    service = CryptoService(master_key_base64=master_key)

    # 10 bytes apenas
    short_payload_b64 = base64.b64encode(b"0123456789").decode("utf-8")
    with pytest.raises(DecryptionError, match="inferior ao nonce mínimo"):
        service.decrypt(short_payload_b64)


def test_decrypt_unexpected_exception_raises_decryption_error() -> None:
    """Garante que qualquer erro não esperado na decifragem seja envelopado em DecryptionError."""
    from unittest.mock import MagicMock

    master_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    service = CryptoService(master_key_base64=master_key)

    encrypted = service.encrypt("SafeString")
    mock_gcm = MagicMock()
    mock_gcm.decrypt.side_effect = RuntimeError("Falha inesperada de decodificação")
    service._aesgcm = mock_gcm

    with pytest.raises(DecryptionError, match="Erro inesperado durante a decifragem"):
        service.decrypt(encrypted)
