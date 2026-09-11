"""Adaptador de autenticação Firebase Auth (Hexagonal Architecture).

Valida os ID Tokens JWT emitidos pelo Firebase Authentication (Google OAuth 2.0)
e extrai os claims do perfil do usuário para o contexto da requisição.
"""

from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.ports.auth_port import AuthError, AuthPort, AuthUser, InvalidTokenError


class FirebaseAuthAdapter(AuthPort):
    """Implementação concreta de AuthPort para validação de tokens Firebase.

    Attributes:
        _firebase_project_id: ID do projeto Firebase para validação de audiência.
        _jwks_client: Cliente PyJWKClient para recuperação de chaves públicas oficiais do Google.
        _public_key: Chave pública opcional injetada diretamente (ex: testes sem rede).
    """

    GOOGLE_JWKS_URL = (
        "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
    )

    def __init__(
        self,
        firebase_project_id: str = "thothcvs-ai",
        jwks_client: PyJWKClient | None = None,
        public_key: Any | None = None,
    ) -> None:
        """Inicializa o adaptador com o identificador do projeto Firebase e JWKS.

        Args:
            firebase_project_id: Identificador do projeto Firebase Auth no Google Cloud.
            jwks_client: Cliente JWKS opcional para customização ou mocks.
            public_key: Chave pública PEM/RSA opcional injetada diretamente para testes.
        """
        self._firebase_project_id = firebase_project_id
        self._public_key = public_key
        self._jwks_client = jwks_client or PyJWKClient(self.GOOGLE_JWKS_URL)

    def _decode_and_verify(self, token: str) -> dict[str, Any]:
        """Decodifica e valida criptograficamente o JWT recebido.

        Args:
            token: String JWT pura informada no header Authorization Bearer.

        Returns:
            dict[str, Any]: Dicionário de claims validados do token.

        Raises:
            InvalidTokenError: Se o token for malformado, expirado ou com assinatura inválida.
        """
        # Em ambiente de desenvolvimento/teste, aceita tokens mockados com payload em JSON
        if settings.ENVIRONMENT in ("development", "test") and token.startswith("mock_"):
            return {
                "sub": f"mock_uid_{token}",
                "email": f"{token}@example.com",
                "name": "Mock Developer",
            }

        try:
            unverified_headers = jwt.get_unverified_header(token)
            if not unverified_headers.get("alg"):
                raise InvalidTokenError("Token JWT com cabeçalho de algoritmo ausente.")

            if self._public_key is not None:
                signing_key = self._public_key
            else:
                signing_key_obj = self._jwks_client.get_signing_key_from_jwt(token)
                signing_key = signing_key_obj.key

            claims = jwt.decode(
                token,
                key=signing_key,
                algorithms=["RS256"],
                audience=self._firebase_project_id,
                issuer=f"https://securetoken.google.com/{self._firebase_project_id}",
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
            return claims
        except jwt.ExpiredSignatureError as exc:
            raise InvalidTokenError("O token Firebase informado expirou.") from exc
        except (jwt.PyJWTError, Exception) as exc:
            raise InvalidTokenError(f"Token Firebase inválido: {exc}") from exc

    async def verify_token(self, token: str) -> AuthUser:
        """Verifica a autenticidade do token Firebase e devolve o AuthUser tipado.

        Args:
            token: ID Token do Firebase.

        Returns:
            AuthUser: Instância contendo UID, e-mail e nome do usuário.

        Raises:
            InvalidTokenError: Se o token falhar na validação estrutural ou temporal.
            AuthError: Se o token não contiver o identificador ou e-mail do usuário.
        """
        if not token or not token.strip():
            raise InvalidTokenError("Token de autorização vazio.")

        claims = self._decode_and_verify(token)

        uid = claims.get("sub") or claims.get("user_id")
        email = claims.get("email")

        if not uid:
            raise AuthError("Token não contém o identificador único (sub) do usuário.")

        if not email:
            raise AuthError("Token não contém o e-mail verificado do usuário.")

        full_name = claims.get("name") or email.split("@")[0].capitalize()
        picture_url = claims.get("picture")

        return AuthUser(
            uid=str(uid),
            email=str(email),
            full_name=str(full_name),
            picture_url=str(picture_url) if picture_url else None,
        )
