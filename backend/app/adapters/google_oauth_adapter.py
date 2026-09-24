"""Adaptador concreto para Google OAuth 2.0 (Hexagonal Architecture).

Implementa a porta OAuthPort utilizando chamadas HTTP assíncronas aos endpoints
oficiais do Google Identity (OpenID Connect / OAuth 2.0).
"""

import time
import urllib.parse
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.ports.oauth_port import OAuthError, OAuthPort, OAuthUserInfo

logger = get_logger("google_oauth_adapter")


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

        start_time = time.perf_counter()
        try:
            if client is not None:
                resp = await client.post(self.TOKEN_URL, data=payload)
            else:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    resp = await http_client.post(self.TOKEN_URL, data=payload)

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if resp.status_code != 200:
                logger.error(
                    "oauth_token_exchange_failed",
                    provider="google",
                    status_code=resp.status_code,
                    duration_ms=duration_ms,
                )
                raise OAuthError(
                    f"Google OAuth token exchange falhou (status {resp.status_code}): {resp.text}"
                )

            logger.info(
                "oauth_token_exchange_success",
                provider="google",
                duration_ms=duration_ms,
            )
            return resp.json()  # type: ignore[no-any-return]
        except OAuthError:
            raise
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "oauth_token_exchange_network_error",
                provider="google",
                duration_ms=duration_ms,
                error=str(exc),
                exc_info=True,
            )
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

        start_time = time.perf_counter()
        try:
            if client is not None:
                resp = await client.get(self.USERINFO_URL, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    resp = await http_client.get(self.USERINFO_URL, headers=headers)

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if resp.status_code != 200:
                logger.error(
                    "oauth_user_info_fetch_failed",
                    provider="google",
                    status_code=resp.status_code,
                    duration_ms=duration_ms,
                )
                raise OAuthError(
                    f"Falha ao obter perfil do usuário no Google (status {resp.status_code}): "
                    f"{resp.text}"
                )

            data: dict[str, Any] = resp.json()
            sub = data.get("sub")
            email = data.get("email")
            if not sub or not email:
                logger.warning(
                    "oauth_user_info_incomplete",
                    provider="google",
                    has_sub=bool(sub),
                    has_email=bool(email),
                )
                raise OAuthError("Google UserInfo não retornou sub ou email válidos.")

            is_verified = data.get("email_verified")
            if is_verified is not True and str(is_verified).lower() != "true":
                logger.warning(
                    "oauth_unverified_email_rejected",
                    provider="google",
                    sub=str(sub),
                )
                raise OAuthError("O e-mail retornado pela conta Google não está verificado.")

            logger.info(
                "oauth_user_info_fetch_success",
                provider="google",
                duration_ms=duration_ms,
            )
            return OAuthUserInfo(
                sub=str(sub),
                email=str(email),
                full_name=str(data.get("name") or email),
                picture_url=data.get("picture"),
            )
        except OAuthError:
            raise
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "oauth_user_info_network_error",
                provider="google",
                duration_ms=duration_ms,
                error=str(exc),
                exc_info=True,
            )
            raise OAuthError(f"Erro ao consultar perfil no Google OpenID: {exc}") from exc
