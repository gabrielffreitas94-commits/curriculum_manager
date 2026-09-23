"""Testes unitários para o adaptador GoogleOAuthAdapter."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.adapters.google_oauth_adapter import GoogleOAuthAdapter
from app.ports.oauth_port import OAuthError, OAuthUserInfo


def test_google_oauth_adapter_get_authorization_url() -> None:
    """Valida a construção da URL de autorização oficial do Google."""
    adapter = GoogleOAuthAdapter(
        client_id="test-client-id",
        client_secret="test-client-secret",
        redirect_uri="http://localhost:8000/callback",
    )

    # Sem state
    url = adapter.get_authorization_url()
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=test-client-id" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fcallback" in url
    assert "response_type=code" in url
    assert "scope=openid+email+profile" in url
    assert "prompt=select_account" in url
    assert "state=" not in url

    # Com state
    url_with_state = adapter.get_authorization_url(state="csrf_state_123")
    assert "state=csrf_state_123" in url_with_state


@pytest.mark.asyncio
async def test_google_oauth_adapter_exchange_code_success() -> None:
    """Valida troca de código por token com resposta 200 OK do Google."""
    adapter = GoogleOAuthAdapter(
        client_id="test-client", client_secret="test-secret", redirect_uri="http://test/cb"
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "mock_acc_tok", "id_token": "mock_id_tok"}
    mock_client.post.return_value = mock_resp

    result = await adapter.exchange_code("valid_code_123", client=mock_client)
    assert result["access_token"] == "mock_acc_tok"
    assert result["id_token"] == "mock_id_tok"
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_google_oauth_adapter_exchange_code_http_error() -> None:
    """Valida lançamento de OAuthError caso o Google retorne status diferente de 200."""
    adapter = GoogleOAuthAdapter(
        client_id="test-client", client_secret="test-secret", redirect_uri="http://test/cb"
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 400
    mock_resp.text = '{"error": "invalid_grant"}'
    mock_client.post.return_value = mock_resp

    with pytest.raises(OAuthError, match="Google OAuth token exchange falhou"):
        await adapter.exchange_code("invalid_code", client=mock_client)


@pytest.mark.asyncio
async def test_google_oauth_adapter_exchange_code_network_error() -> None:
    """Valida lançamento de OAuthError caso ocorra erro de conexão/rede."""
    adapter = GoogleOAuthAdapter()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.ConnectError("Connection refused")

    with pytest.raises(OAuthError, match="Erro de conexão durante troca de código OAuth"):
        await adapter.exchange_code("code", client=mock_client)


@pytest.mark.asyncio
async def test_google_oauth_adapter_exchange_code_default_client() -> None:
    """Valida execução da troca de código instanciando cliente padrão."""
    adapter = GoogleOAuthAdapter()
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "token_ok"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await adapter.exchange_code("code_123")
        assert result["access_token"] == "token_ok"


@pytest.mark.asyncio
async def test_google_oauth_adapter_fetch_user_info_success() -> None:
    """Valida recuperação e parsing dos dados de perfil do usuário."""
    adapter = GoogleOAuthAdapter()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "sub": "google_sub_999",
        "email": "teste@gmail.com",
        "name": "Nome Usuário",
        "picture": "https://avatar.google.com/pic.jpg",
    }
    mock_client.get.return_value = mock_resp

    info: OAuthUserInfo = await adapter.fetch_user_info("mock_token", client=mock_client)
    assert info.sub == "google_sub_999"
    assert info.email == "teste@gmail.com"
    assert info.full_name == "Nome Usuário"
    assert info.picture_url == "https://avatar.google.com/pic.jpg"


@pytest.mark.asyncio
async def test_google_oauth_adapter_fetch_user_info_fallback_name() -> None:
    """Valida que o e-mail é utilizado como fallback se name não vier no payload."""
    adapter = GoogleOAuthAdapter()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "sub": "google_sub_888",
        "email": "noname@gmail.com",
    }
    mock_client.get.return_value = mock_resp

    info = await adapter.fetch_user_info("mock_token", client=mock_client)
    assert info.sub == "google_sub_888"
    assert info.email == "noname@gmail.com"
    assert info.full_name == "noname@gmail.com"
    assert info.picture_url is None


@pytest.mark.asyncio
async def test_google_oauth_adapter_fetch_user_info_missing_fields() -> None:
    """Valida lançamento de OAuthError se sub ou email estiverem ausentes."""
    adapter = GoogleOAuthAdapter()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"name": "No Sub and Email"}
    mock_client.get.return_value = mock_resp

    with pytest.raises(OAuthError, match="Google UserInfo não retornou sub ou email válidos"):
        await adapter.fetch_user_info("mock_token", client=mock_client)


@pytest.mark.asyncio
async def test_google_oauth_adapter_fetch_user_info_http_error() -> None:
    """Valida lançamento de OAuthError caso o Google retorne erro HTTP."""
    adapter = GoogleOAuthAdapter()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_client.get.return_value = mock_resp

    with pytest.raises(OAuthError, match="Falha ao obter perfil do usuário no Google"):
        await adapter.fetch_user_info("bad_token", client=mock_client)


@pytest.mark.asyncio
async def test_google_oauth_adapter_fetch_user_info_network_error() -> None:
    """Valida lançamento de OAuthError caso ocorra erro de conexão/rede."""
    adapter = GoogleOAuthAdapter()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.side_effect = httpx.ConnectError("Network timeout")

    with pytest.raises(OAuthError, match="Erro ao consultar perfil no Google OpenID"):
        await adapter.fetch_user_info("token", client=mock_client)


@pytest.mark.asyncio
async def test_google_oauth_adapter_fetch_user_info_default_client() -> None:
    """Valida execução da consulta de perfil instanciando cliente padrão."""
    adapter = GoogleOAuthAdapter()
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "sub": "sub_def",
        "email": "def@gmail.com",
        "name": "Default Client",
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        info = await adapter.fetch_user_info("token_def")
        assert info.sub == "sub_def"
        assert info.email == "def@gmail.com"
