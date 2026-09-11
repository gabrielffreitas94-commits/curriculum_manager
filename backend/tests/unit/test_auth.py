"""Testes unitários rigorosos para a porta e o adaptador FirebaseAuthAdapter.

Cobre 100% da lógica interna de parsing de JWT, decodificação real, tratamento de expiração,
prefixos de mock de desenvolvimento e validações de claims do usuário.
"""

import time

import jwt
import pytest

from app.adapters.firebase_auth_adapter import FirebaseAuthAdapter
from app.ports.auth_port import AuthError, AuthUser, InvalidTokenError


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
async def test_verify_token_real_jwt_valid() -> None:
    """Garante a decodificação real de um JWT válido pelo FirebaseAuthAdapter."""
    adapter = FirebaseAuthAdapter()

    # Gera um JWT real assinado
    payload = {
        "sub": "firebase_user_999",
        "email": "sarah.connor@sky.net",
        "name": "Sarah Connor",
        "picture": "https://avatar.url/sarah.jpg",
        "exp": int(time.time()) + 3600,
    }
    encoded_token = jwt.encode(payload, "01234567890123456789012345678901", algorithm="HS256")

    auth_user = await adapter.verify_token(encoded_token)

    assert auth_user.uid == "firebase_user_999"
    assert auth_user.email == "sarah.connor@sky.net"
    assert auth_user.full_name == "Sarah Connor"
    assert auth_user.picture_url == "https://avatar.url/sarah.jpg"


@pytest.mark.asyncio
async def test_verify_token_fallback_name_from_email() -> None:
    """Garante que a ausência do claim 'name' gere o nome a partir do prefixo do e-mail."""
    adapter = FirebaseAuthAdapter()

    payload = {
        "sub": "user_without_name",
        "email": "carlos.silva@empresa.com",
        "exp": int(time.time()) + 3600,
    }
    encoded_token = jwt.encode(payload, "01234567890123456789012345678901", algorithm="HS256")

    auth_user = await adapter.verify_token(encoded_token)

    assert auth_user.uid == "user_without_name"
    assert auth_user.email == "carlos.silva@empresa.com"
    assert auth_user.full_name == "Carlos.silva"


@pytest.mark.asyncio
async def test_verify_token_expired_jwt_raises_invalid_token() -> None:
    """Garante que um token com 'exp' expirado levante InvalidTokenError com mensagem clara."""
    adapter = FirebaseAuthAdapter()

    # Gera token expirado (exp no passado)
    payload = {
        "sub": "expired_user",
        "email": "old@thothcvs.ai",
        "exp": int(time.time()) - 1000,
    }
    expired_token = jwt.encode(payload, "secret_key", algorithm="HS256")

    with pytest.raises(InvalidTokenError, match="O token Firebase informado expirou"):
        await adapter.verify_token(expired_token)


@pytest.mark.asyncio
async def test_verify_token_malformed_jwt_raises_invalid_token() -> None:
    """Garante que string JWT inválida ou corrompida levante InvalidTokenError."""
    adapter = FirebaseAuthAdapter()
    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token("invalid.jwt.payload.string")


@pytest.mark.asyncio
async def test_verify_token_missing_sub_raises_auth_error() -> None:
    """Garante que um JWT sem claim 'sub' levante AuthError."""
    adapter = FirebaseAuthAdapter()

    payload = {
        "email": "user.without.sub@thothcvs.ai",
        "exp": int(time.time()) + 3600,
    }
    token_without_sub = jwt.encode(payload, "secret_key", algorithm="HS256")

    with pytest.raises(AuthError, match="Token não contém o identificador único"):
        await adapter.verify_token(token_without_sub)


@pytest.mark.asyncio
async def test_verify_token_missing_email_raises_auth_error() -> None:
    """Garante que um JWT sem claim 'email' levante AuthError."""
    adapter = FirebaseAuthAdapter()

    payload = {
        "sub": "user_without_email_123",
        "exp": int(time.time()) + 3600,
    }
    token_without_email = jwt.encode(payload, "secret_key", algorithm="HS256")

    with pytest.raises(AuthError, match="Token não contém o e-mail"):
        await adapter.verify_token(token_without_email)
