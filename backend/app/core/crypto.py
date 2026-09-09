"""Serviço criptográfico para proteção de segredos e chaves de API em repouso.

Implementa cifragem e decifragem autenticada utilizando AES-GCM-256
(Advanced Encryption Standard no modo Galois/Counter Mode).
Garante confidencialidade, integridade e proteção contra ataques de adulteração (AEAD).
"""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


class CryptoError(Exception):
    """Exceção base para falhas operacionais do módulo criptográfico."""

    pass


class DecryptionError(CryptoError):
    """Exceção lançada quando a decifragem falha devido a adulteração ou chave incorreta."""

    pass


class CryptoService:
    """Gerencia a cifragem e decifragem autenticada de strings sensíveis usando AES-GCM-256.

    Attributes:
        _aesgcm: Instância inicializada do algoritmo AESGCM da biblioteca cryptography.

    Security Considerations:
        - Cada operação de cifragem gera um nonce pseudoaleatório único de 12 bytes (96 bits).
        - O nonce NUNCA é reutilizado para a mesma chave mestra.
        - O ciphertext armazena o nonce nos primeiros 12 bytes, seguido pelo payload cifrado
          e pela tag de autenticação de 16 bytes gerenciada pelo AESGCM.
    """

    NONCE_LENGTH_BYTES = 12

    def __init__(self, master_key_base64: str) -> None:
        """Inicializa o serviço validando o tamanho e decodificação da chave mestra.

        Args:
            master_key_base64: Chave mestra de 32 bytes (256 bits) codificada em Base64.

        Raises:
            ValueError: Se a chave fornecida não contiver exatamente 32 bytes após decodificação.
        """
        try:
            raw_key = base64.b64decode(master_key_base64)
        except Exception as exc:
            raise ValueError("A chave mestra informada não é um Base64 válido.") from exc

        if len(raw_key) != 32:
            raise ValueError(
                f"A chave mestra deve conter exatamente 32 bytes (256 bits). "
                f"Tamanho recebido: {len(raw_key)} bytes."
            )

        self._aesgcm = AESGCM(raw_key)

    def encrypt(self, plaintext: str) -> str:
        """Cifra uma string em texto plano e retorna a representação compactada em Base64.

        Args:
            plaintext: Texto a ser protegido (ex: API key do Google Gemini).

        Returns:
            str: String em Base64 contendo `nonce + ciphertext + auth_tag`.

        Security Considerations:
            Gera um nonce novo a cada chamada via `os.urandom`.
        """
        nonce = os.urandom(self.NONCE_LENGTH_BYTES)
        raw_plaintext = plaintext.encode("utf-8")
        ciphertext_with_tag = self._aesgcm.encrypt(nonce, raw_plaintext, None)

        # Concatena nonce (12B) + ciphertext com tag (variável)
        payload = nonce + ciphertext_with_tag
        return base64.b64encode(payload).decode("utf-8")

    def decrypt(self, encrypted_base64: str) -> str:
        """Decifra um payload protegido e valida a integridade da tag de autenticação.

        Args:
            encrypted_base64: String Base64 gerada previamente pelo método `encrypt`.

        Returns:
            str: O texto plano original restaurado.

        Raises:
            DecryptionError: Se o payload estiver corrompido, adulterado ou a chave for inválida.
        """
        try:
            payload = base64.b64decode(encrypted_base64)
        except Exception as exc:
            raise DecryptionError(
                "Payload criptografado possui codificação Base64 inválida."
            ) from exc

        if len(payload) <= self.NONCE_LENGTH_BYTES:
            raise DecryptionError("Payload criptografado possui tamanho inferior ao nonce mínimo.")

        nonce = payload[: self.NONCE_LENGTH_BYTES]
        ciphertext_with_tag = payload[self.NONCE_LENGTH_BYTES :]

        try:
            raw_plaintext = self._aesgcm.decrypt(nonce, ciphertext_with_tag, None)
            return raw_plaintext.decode("utf-8")
        except InvalidTag as exc:
            raise DecryptionError(
                "Falha de autenticação ou payload corrompido ao decifrar segredo."
            ) from exc
        except Exception as exc:
            raise DecryptionError("Erro inesperado durante a decifragem do segredo.") from exc


# Instância global do serviço de criptografia baseada na chave do ambiente
crypto_service = CryptoService(master_key_base64=settings.MASTER_ENCRYPTION_KEY)
