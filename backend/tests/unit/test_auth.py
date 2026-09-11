"""Testes unitários rigorosos para a porta e o adaptador FirebaseAuthAdapter.

Cobre 100% da lógica interna de parsing de JWT, verificação criptográfica RS256,
defesa contra falsificação de assinatura, validação de audiência/emissor,
tratamento de expiração, prefixos de mock e validações de claims do usuário.
"""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.adapters.firebase_auth_adapter import FirebaseAuthAdapter
from app.core.config import settings
from app.ports.auth_port import AuthError, AuthUser, InvalidTokenError


@pytest.fixture(scope="session")
def rsa_keys() -> tuple[bytes, bytes]:
    """Gera par de chaves RSA legítimo para testes de assinatura e verificação."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem_private, pem_public


@pytest.fixture(scope="session")
def attacker_rsa_private_key() -> bytes:
    """Gera chave privada de um invasor para testar rejeição de assinatura forjada."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def test_auth_user_dataclass() -> None:
    """Valida a estrutura imutável de usuário autenticado do domínio."""
    user = AuthUser(
        uid="firebase_uid_abc",
        email="dev@thothcvs.ai",
        full_name="Thoth Dev",
        picture_url="https://avatar.url/img.png",
    )
    assert user.uid == "firebase_uid_abc"
    assert user.email == "dev@thothcvs.ai"
    assert user.full_name == "Thoth Dev"
    assert user.picture_url == "https://avatar.url/img.png"


@pytest.mark.asyncio
async def test_verify_token_empty_or_whitespace_raises_invalid_token() -> None:
    """Garante que tokens vazios ou com espaços levantem InvalidTokenError imediatamente."""
    adapter = FirebaseAuthAdapter()
    with pytest.raises(InvalidTokenError, match="Token de autorização vazio"):
        await adapter.verify_token("")

    with pytest.raises(InvalidTokenError, match="Token de autorização vazio"):
        await adapter.verify_token("    ")


@pytest.mark.asyncio
async def test_verify_token_mock_prefix_in_dev_test_env() -> None:
    """Valida o atalho de ambiente de teste para tokens iniciados com 'mock_'."""
    adapter = FirebaseAuthAdapter()
    auth_user = await adapter.verify_token("mock_developer_user")

    assert auth_user.uid == "mock_uid_mock_developer_user"
    assert auth_user.email == "mock_developer_user@example.com"
    assert auth_user.full_name == "Mock Developer"
    assert auth_user.picture_url is None


@pytest.mark.asyncio
async def test_verify_token_mock_prefix_in_production_rejected(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    """Garante que tokens mock sejam rejeitados e passem por verificação rigorosa em produção."""
    _, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(public_key=pem_public)
    with (
        patch.object(settings, "ENVIRONMENT", "production"),
        pytest.raises(InvalidTokenError, match="Token Firebase inválido"),
    ):
        await adapter.verify_token("mock_attacker_token")


@pytest.mark.asyncio
async def test_verify_token_real_jwt_valid(rsa_keys: tuple[bytes, bytes]) -> None:
    """Garante a validação criptográfica RS256 de um JWT legítimo pelo FirebaseAuthAdapter."""
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "firebase_user_999",
        "email": "sarah.connor@sky.net",
        "name": "Sarah Connor",
        "picture": "https://avatar.url/sarah.jpg",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    encoded_token = jwt.encode(payload, pem_private, algorithm="RS256")

    auth_user = await adapter.verify_token(encoded_token)

    assert auth_user.uid == "firebase_user_999"
    assert auth_user.email == "sarah.connor@sky.net"
    assert auth_user.full_name == "Sarah Connor"
    assert auth_user.picture_url == "https://avatar.url/sarah.jpg"


@pytest.mark.asyncio
async def test_verify_token_valid_via_jwks_client(rsa_keys: tuple[bytes, bytes]) -> None:
    """Valida a resolução da chave pública através de PyJWKClient quando
    public_key não é injetada.
    """
    pem_private, pem_public = rsa_keys
    mock_jwks = MagicMock()
    mock_signing_key = MagicMock()
    mock_signing_key.key = pem_public
    mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key

    adapter = FirebaseAuthAdapter(
        firebase_project_id="thothcvs-ai",
        jwks_client=mock_jwks,
    )

    payload = {
        "sub": "jwks_verified_user",
        "email": "jwks@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    encoded_token = jwt.encode(payload, pem_private, algorithm="RS256")

    auth_user = await adapter.verify_token(encoded_token)

    assert auth_user.uid == "jwks_verified_user"
    assert auth_user.email == "jwks@thothcvs.ai"
    assert auth_user.full_name == "Jwks"
    mock_jwks.get_signing_key_from_jwt.assert_called_once_with(encoded_token)


@pytest.mark.asyncio
async def test_verify_token_forged_signature_rejected(
    rsa_keys: tuple[bytes, bytes],
    attacker_rsa_private_key: bytes,
) -> None:
    """Garante que um token assinado por chave privada não autorizada seja
    rejeitado categoricamente.
    """
    _, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "victim_user_123",
        "email": "victim@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    forged_token = jwt.encode(payload, attacker_rsa_private_key, algorithm="RS256")

    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token(forged_token)


@pytest.mark.asyncio
async def test_verify_token_algorithm_confusion_rejected(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    """Garante rejeição imediata contra ataques de confusão de algoritmo
    (ex: HMAC HS256 em vez de RS256).
    """
    _, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "victim_user_123",
        "email": "victim@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    # Tenta enviar token HS256 quando o sistema só aceita RS256
    confused_token = jwt.encode(
        payload,
        "symmetric_secret_key_at_least_32_bytes_long_123",
        algorithm="HS256",
    )

    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token(confused_token)


@pytest.mark.asyncio
async def test_verify_token_wrong_audience_rejected(rsa_keys: tuple[bytes, bytes]) -> None:
    """Garante que tokens emitidos para outros projetos Firebase sejam rejeitados."""
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "user_other_project",
        "email": "user@other.com",
        "aud": "malicious-foreign-project",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    wrong_aud_token = jwt.encode(payload, pem_private, algorithm="RS256")

    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token(wrong_aud_token)


@pytest.mark.asyncio
async def test_verify_token_wrong_issuer_rejected(rsa_keys: tuple[bytes, bytes]) -> None:
    """Garante que tokens com emissor (iss) forjado sejam rejeitados."""
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "user_fake_iss",
        "email": "user@fake.com",
        "aud": "thothcvs-ai",
        "iss": "https://fake-issuer.attacker.com",
        "exp": int(time.time()) + 3600,
    }
    wrong_iss_token = jwt.encode(payload, pem_private, algorithm="RS256")

    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token(wrong_iss_token)


@pytest.mark.asyncio
async def test_verify_token_fallback_name_from_email(rsa_keys: tuple[bytes, bytes]) -> None:
    """Garante que a ausência do claim 'name' gere o nome a partir do prefixo do e-mail."""
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "user_without_name",
        "email": "carlos.silva@empresa.com",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    encoded_token = jwt.encode(payload, pem_private, algorithm="RS256")

    auth_user = await adapter.verify_token(encoded_token)

    assert auth_user.uid == "user_without_name"
    assert auth_user.email == "carlos.silva@empresa.com"
    assert auth_user.full_name == "Carlos.silva"


@pytest.mark.asyncio
async def test_verify_token_expired_jwt_raises_invalid_token(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    """Garante que um token com 'exp' expirado levante InvalidTokenError com mensagem clara."""
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "expired_user",
        "email": "old@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) - 1000,
    }
    expired_token = jwt.encode(payload, pem_private, algorithm="RS256")

    with pytest.raises(InvalidTokenError, match="O token Firebase informado expirou"):
        await adapter.verify_token(expired_token)


@pytest.mark.asyncio
async def test_verify_token_malformed_jwt_raises_invalid_token() -> None:
    """Garante que string JWT inválida ou corrompida levante InvalidTokenError."""
    adapter = FirebaseAuthAdapter()
    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token("invalid.jwt.payload.string")


@pytest.mark.asyncio
async def test_verify_token_missing_sub_raises_auth_error(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    """Garante que um JWT sem claim 'sub' levante AuthError."""
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "email": "user.without.sub@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    token_without_sub = jwt.encode(payload, pem_private, algorithm="RS256")

    with pytest.raises(AuthError, match="Token não contém o identificador único"):
        await adapter.verify_token(token_without_sub)


@pytest.mark.asyncio
async def test_verify_token_missing_email_raises_auth_error(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    """Garante que um JWT sem claim 'email' levante AuthError."""
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "user_without_email_123",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    token_without_email = jwt.encode(payload, pem_private, algorithm="RS256")

    with pytest.raises(AuthError, match="Token não contém o e-mail"):
        await adapter.verify_token(token_without_email)


@pytest.mark.asyncio
async def test_verify_token_missing_alg_header() -> None:
    """Garante que um JWT com header sem 'alg' levante InvalidTokenError."""
    adapter = FirebaseAuthAdapter()
    with (
        patch("jwt.get_unverified_header", return_value={}),
        pytest.raises(InvalidTokenError, match="Token JWT com cabeçalho de algoritmo ausente"),
    ):
        await adapter.verify_token("some.valid.jwt")


def test_firebase_auth_adapter_default_attributes() -> None:
    """Valida a inicialização padrão do adaptador com o endpoint oficial JWKS do Google."""
    adapter = FirebaseAuthAdapter()
    assert adapter._firebase_project_id == "thothcvs-ai"
    assert adapter._public_key is None
    assert adapter._jwks_client is not None
