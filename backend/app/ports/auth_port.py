"""Porta abstrata de autenticação e identidade de usuários (Hexagonal Architecture).

Define o contrato que qualquer provedor de identidade (Firebase Auth, Auth0, Mock)
deve implementar para validação de credenciais de acesso no ThothCVs AI.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class AuthError(Exception):
    """Exceção base para erros ocorridos durante o fluxo de autenticação."""

    pass


class InvalidTokenError(AuthError):
    """Lançada quando um token JWT de autenticação é forjado, expirado ou inválido."""

    pass


@dataclass(frozen=True)
class AuthUser:
    """Representação imutável dos dados do usuário extraídos do token de autenticação.

    Attributes:
        uid: Identificador único universal do provedor de identidade (Firebase UID).
        email: E-mail primário do usuário autenticado.
        full_name: Nome completo retornado pelo provedor ou derivado do e-mail.
        picture_url: URL opcional da foto de perfil (Google Account).
    """

    uid: str
    email: str
    full_name: str
    picture_url: str | None = None


class AuthPort(ABC):
    """Interface abstrata para validação de credenciais e tokens de acesso."""

    @abstractmethod
    async def verify_token(self, token: str) -> AuthUser:
        """Verifica criptograficamente o token JWT e retorna o usuário autenticado.

        Args:
            token: Token JWT de identidade (Bearer token).

        Returns:
            AuthUser: Instância contendo os dados validados do usuário.

        Raises:
            InvalidTokenError: Se a assinatura, emissor ou validade temporal falharem.
            AuthError: Se claims obrigatórios estiverem ausentes no token.
        """
        pass

    @abstractmethod
    async def revoke_user_tokens(self, uid: str) -> None:
        """Revoga todos os tokens e sessões ativas do usuário no provedor de identidade.

        Args:
            uid: Identificador único do usuário no provedor (Firebase UID).
        """
        pass
