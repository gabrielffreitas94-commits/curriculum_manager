"""Testes unitários e de cobertura para o AuthService."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.models import User
from app.ports.auth_port import AuthPort, AuthUser, InvalidTokenError
from app.ports.oauth_port import OAuthError, OAuthPort, OAuthUserInfo
from app.services.auth_service import AuthService


def test_auth_service_create_session_jwt() -> None:
    """Valida emissão correta de token JWT de sessão."""
    service = AuthService(db=MagicMock(spec=AsyncSession))
    token = service.create_session_jwt(uid="user_uid_123", email="user@teste.com")

    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"], issuer="thothcvs-web")
    assert payload["sub"] == "user_uid_123"
    assert payload["email"] == "user@teste.com"
    assert payload["iss"] == "thothcvs-web"
    assert "exp" in payload
    assert "iat" in payload


@pytest.mark.asyncio
async def test_auth_service_get_authenticated_user_empty_token() -> None:
    """Valida que tokens vazios ou nulos retornam None sem erro."""
    service = AuthService(db=MagicMock(spec=AsyncSession))
    assert await service.get_authenticated_user(None) is None
    assert await service.get_authenticated_user("") is None
    assert await service.get_authenticated_user("   ") is None


@pytest.mark.asyncio
async def test_auth_service_get_authenticated_user_jwt_success() -> None:
    """Valida resolução de usuário a partir de JWT de sessão válido."""
    db_mock = MagicMock(spec=AsyncSession)
    user_mock = User(id=uuid.uuid4(), firebase_uid="sub_456", email="valid@test.com")
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = user_mock
    db_mock.execute = AsyncMock(return_value=mock_res)

    service = AuthService(db=db_mock)
    token = service.create_session_jwt(uid="sub_456", email="valid@test.com")

    user = await service.get_authenticated_user(token)
    assert user == user_mock
    assert user.firebase_uid == "sub_456"


@pytest.mark.asyncio
async def test_auth_service_get_authenticated_user_jwt_user_not_found() -> None:
    """Valida retorno None quando o sub do JWT não existe no banco."""
    db_mock = MagicMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db_mock.execute = AsyncMock(return_value=mock_res)

    service = AuthService(db=db_mock)
    token = service.create_session_jwt(uid="sub_unknown", email="unknown@test.com")

    user = await service.get_authenticated_user(token)
    assert user is None


@pytest.mark.asyncio
async def test_auth_service_get_authenticated_user_fallback_auth_port_success() -> None:
    """Valida resolução de usuário via fallback da AuthPort quando o token não é JWT próprio."""
    db_mock = MagicMock(spec=AsyncSession)
    user_mock = User(id=uuid.uuid4(), firebase_uid="mock_uid_123", email="mock@test.com")
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = user_mock
    db_mock.execute = AsyncMock(return_value=mock_res)

    auth_port_mock = MagicMock(spec=AuthPort)
    auth_port_mock.verify_token = AsyncMock(
        return_value=AuthUser(uid="mock_uid_123", email="mock@test.com", full_name="Mock User")
    )

    service = AuthService(db=db_mock, auth_port=auth_port_mock)
    user = await service.get_authenticated_user("legacy_mock_token")

    assert user == user_mock
    auth_port_mock.verify_token.assert_called_once_with("legacy_mock_token")


@pytest.mark.asyncio
async def test_auth_service_get_authenticated_user_fallback_no_port_returns_none() -> None:
    """Valida retorno None para tokens não-JWT quando auth_port não foi fornecida."""
    db_mock = MagicMock(spec=AsyncSession)
    service = AuthService(db=db_mock, auth_port=None)

    assert await service.get_authenticated_user("not_a_jwt_token") is None


@pytest.mark.asyncio
async def test_auth_service_get_authenticated_user_fallback_port_exception() -> None:
    """Valida retorno None quando auth_port lança exceção ao verificar token."""
    db_mock = MagicMock(spec=AsyncSession)
    auth_port_mock = MagicMock(spec=AuthPort)
    auth_port_mock.verify_token = AsyncMock(side_effect=InvalidTokenError("Token expirado"))

    service = AuthService(db=db_mock, auth_port=auth_port_mock)
    assert await service.get_authenticated_user("invalid_bearer_token") is None


@pytest.mark.asyncio
async def test_auth_service_authenticate_oauth_user_missing_access_token() -> None:
    """Valida que ausência de access_token levanta OAuthError."""
    service = AuthService(db=MagicMock(spec=AsyncSession))
    oauth_port_mock = MagicMock(spec=OAuthPort)
    oauth_port_mock.exchange_code = AsyncMock(return_value={"id_token": "only_id"})

    with pytest.raises(OAuthError, match="Token de acesso ausente"):
        await service.authenticate_oauth_user(oauth_port_mock, code="code_123")


@pytest.mark.asyncio
async def test_auth_service_authenticate_oauth_user_new_user() -> None:
    """Valida provisionamento completo de novo usuário e configurações."""
    db_mock = MagicMock(spec=AsyncSession)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db_mock.execute = AsyncMock(return_value=mock_res)
    db_mock.flush = AsyncMock()
    db_mock.commit = AsyncMock()

    oauth_port_mock = MagicMock(spec=OAuthPort)
    oauth_port_mock.exchange_code = AsyncMock(return_value={"access_token": "acc_tok_ok"})
    oauth_port_mock.fetch_user_info = AsyncMock(
        return_value=OAuthUserInfo(
            sub="sub_new_user",
            email="novo@test.com",
            full_name="Novo Usuário",
        )
    )

    service = AuthService(db=db_mock)
    user, session_token = await service.authenticate_oauth_user(oauth_port_mock, code="valid_code")

    assert user.email == "novo@test.com"
    assert user.firebase_uid == "google_sub_new_user"
    assert isinstance(session_token, str)
    assert len(session_token) > 0
    db_mock.flush.assert_called_once()
    db_mock.commit.assert_called_once()


@pytest.mark.asyncio
async def test_auth_service_authenticate_oauth_user_existing_user_update() -> None:
    """Valida atualização de perfil para usuário já existente."""
    db_mock = MagicMock(spec=AsyncSession)
    existing_user = User(
        id=uuid.uuid4(),
        firebase_uid="old_uid",
        email="existente@test.com",
        full_name="",
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = existing_user
    db_mock.execute = AsyncMock(return_value=mock_res)
    db_mock.commit = AsyncMock()

    oauth_port_mock = MagicMock(spec=OAuthPort)
    oauth_port_mock.exchange_code = AsyncMock(return_value={"access_token": "acc_tok_ok"})
    oauth_port_mock.fetch_user_info = AsyncMock(
        return_value=OAuthUserInfo(
            sub="sub_updated",
            email="existente@test.com",
            full_name="Nome Atualizado",
        )
    )

    service = AuthService(db=db_mock)
    user, session_token = await service.authenticate_oauth_user(oauth_port_mock, code="code_ok")

    assert user == existing_user
    assert user.firebase_uid == "google_sub_updated"
    assert user.full_name == "Nome Atualizado"
    db_mock.commit.assert_called_once()
