"""Testes unitários para o serviço de criptografia simétrica AES-GCM-256."""

import pytest

from app.core.crypto import CryptoService, DecryptionError


def test_encryption_and_decryption_success() -> None:
    """Testa o ciclo completo de cifragem e decifragem de uma chave de API."""
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
    """Garante que qualquer adulteração no texto cifrado ou tag de autenticação falhe."""
    master_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    service = CryptoService(master_key_base64=master_key)

    secret_text = "AIzaSySuperSecretKey"
    encrypted = service.encrypt(secret_text)

    # Altera propositalmente os últimos caracteres do ciphertext Base64
    tampered = encrypted[:-4] + "AAAA"

    with pytest.raises(DecryptionError, match="Falha de autenticação ou payload corrompido"):
        service.decrypt(tampered)


def test_wrong_key_decryption_failure() -> None:
    """Garante que tentar decifrar com uma chave mestra diferente levante DecryptionError."""
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
