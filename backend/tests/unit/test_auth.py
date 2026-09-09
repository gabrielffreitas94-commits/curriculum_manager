"""Testes unitários para a porta de autenticação e adaptador Firebase."""

from unittest.mock import patch

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
async def test_firebase_auth_adapter_valid_token() -> None:
    """Testa a validação bem-sucedida de um token Firebase simulado."""
    adapter = FirebaseAuthAdapter()
    token = "valid_mock_jwt_token"

    mock_claims = {
        "sub": "firebase_123",
        "email": "candidate@thothcvs.ai",
        "name": "Candidate One",
        "picture": "https://lh3.googleusercontent.com/a/photo.jpg",
    }

    with patch.object(adapter, "_decode_and_verify", return_value=mock_claims):
        auth_user = await adapter.verify_token(token)
        assert auth_user.uid == "firebase_123"
        assert auth_user.email == "candidate@thothcvs.ai"
        assert auth_user.full_name == "Candidate One"
        assert auth_user.picture_url == "https://lh3.googleusercontent.com/a/photo.jpg"


@pytest.mark.asyncio
async def test_firebase_auth_adapter_invalid_token() -> None:
    """Garante que um token inválido ou forjado levante InvalidTokenError."""
    adapter = FirebaseAuthAdapter()
    token = "invalid_token"

    with (
        patch.object(
            adapter, "_decode_and_verify", side_effect=InvalidTokenError("Token inválido")
        ),
        pytest.raises(InvalidTokenError, match="Token inválido"),
    ):
        await adapter.verify_token(token)


@pytest.mark.asyncio
async def test_firebase_auth_adapter_missing_claims() -> None:
    """Garante que um token sem campo email ou sub levante AuthError."""
    adapter = FirebaseAuthAdapter()
    token = "incomplete_claims_token"

    # Token sem email
    mock_claims = {
        "sub": "firebase_123",
    }

    with (
        patch.object(adapter, "_decode_and_verify", return_value=mock_claims),
        pytest.raises(AuthError, match="Token não contém o e-mail"),
    ):
        await adapter.verify_token(token)
