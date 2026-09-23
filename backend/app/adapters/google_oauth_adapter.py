"""Adaptador concreto para Google OAuth 2.0 (Hexagonal Architecture).

Implementa a porta OAuthPort utilizando chamadas HTTP assíncronas aos endpoints
oficiais do Google Identity (OpenID Connect / OAuth 2.0).
"""

import urllib.parse
from typing import Any

import httpx

from app.core.config import settings
from app.ports.oauth_port import OAuthError, OAuthPort, OAuthUserInfo


class GoogleOAuthAdapter(OAuthPort):
    """Adaptador de infraestrutura para integração com o Google OAuth 2.0."""

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        """Inicializa o adaptador com credenciais do Google OAuth.

        Args:
            client_id: Client ID da aplicação Google Cloud.
            client_secret: Client Secret da aplicação Google Cloud.
            redirect_uri: URI de callback registrada no Google Cloud Console.
        """
        self._client_id = client_id or settings.GOOGLE_CLIENT_ID
        self._client_secret = client_secret or settings.GOOGLE_CLIENT_SECRET
        self._redirect_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI

    def get_authorization_url(self, state: str | None = None) -> str:
        """Monta a URL de autorização oficial do Google Accounts.

        Args:
            state: Token de estado opcional.

        Returns:
            str: URL completa com os parâmetros exigidos pelo Google.
        """
        params: dict[str, str] = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account",
        }
        if state:
            params["state"] = state
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(
        self, code: str, client: httpx.AsyncClient | None = None
    ) -> dict[str, Any]:
        """Troca o código de autorização por tokens de acesso e id.

        Args:
            code: Código de autorização retornado pelo Google.
            client: Cliente HTTP opcional (para injeção de dependência e testes).

        Returns:
            dict[str, Any]: Payload com access_token, id_token, etc.

        Raises:
            OAuthError: Caso ocorra erro HTTP ou o Google rejeite o código.
        """
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self._redirect_uri,
        }

        try:
            if client is not None:
                resp = await client.post(self.TOKEN_URL, data=payload)
            else:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    resp = await http_client.post(self.TOKEN_URL, data=payload)

            if resp.status_code != 200:
                raise OAuthError(
                    f"Google OAuth token exchange falhou (status {resp.status_code}): {resp.text}"
                )
            return resp.json()  # type: ignore[no-any-return]
        except OAuthError:
            raise
        except Exception as exc:
            raise OAuthError(f"Erro de conexão durante troca de código OAuth: {exc}") from exc

    async def fetch_user_info(
        self, access_token: str, client: httpx.AsyncClient | None = None
    ) -> OAuthUserInfo:
        """Recupera dados de perfil do usuário via Google UserInfo API.

        Args:
            access_token: Token de acesso OAuth 2.0 emitido pelo Google.
            client: Cliente HTTP opcional (para injeção de dependência e testes).

        Returns:
            OAuthUserInfo: Dados canônicos do perfil.

        Raises:
            OAuthError: Caso a requisição falhe ou retorne dados incompletos.
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            if client is not None:
                resp = await client.get(self.USERINFO_URL, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    resp = await http_client.get(self.USERINFO_URL, headers=headers)

            if resp.status_code != 200:
                raise OAuthError(
                    f"Falha ao obter perfil do usuário no Google (status {resp.status_code}): "
                    f"{resp.text}"
                )

            data: dict[str, Any] = resp.json()
            sub = data.get("sub")
            email = data.get("email")
            if not sub or not email:
                raise OAuthError("Google UserInfo não retornou sub ou email válidos.")

            return OAuthUserInfo(
                sub=str(sub),
                email=str(email),
                full_name=str(data.get("name") or email),
                picture_url=data.get("picture"),
            )
        except OAuthError:
            raise
        except Exception as exc:
            raise OAuthError(f"Erro ao consultar perfil no Google OpenID: {exc}") from exc
