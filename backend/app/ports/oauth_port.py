"""Porta abstrata para provedores de autenticação OAuth 2.0 (Hexagonal Architecture).

Define o contrato que qualquer provedor OAuth 2.0 (Google, LinkedIn, GitHub) deve
implementar para autorização, troca de código por tokens e obtenção de perfil.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class OAuthError(Exception):
    """Exceção base para falhas ocorridas durante os fluxos de autorização OAuth."""

    pass


@dataclass(frozen=True)
class OAuthUserInfo:
    """Representação padronizada dos dados de perfil retornados por provedores OAuth.

    Attributes:
        sub: Identificador único universal do usuário no provedor (OpenID subject).
        email: E-mail primário do usuário associado à conta externa.
        full_name: Nome completo exibível do usuário.
        picture_url: URL opcional do avatar ou foto de perfil.
    """

    sub: str
    email: str
    full_name: str
    picture_url: str | None = None


class OAuthPort(ABC):
    """Contrato abstrato para provedores de identidade e autenticação OAuth 2.0."""

    @abstractmethod
    def get_authorization_url(self, state: str | None = None) -> str:
        """Gera a URL oficial de redirecionamento para consentimento do usuário.

        Args:
            state: Token de estado CSRF opcional para validação contra ataques de replay.

        Returns:
            str: URL completa com parâmetros de query para navegação no navegador.
        """
        pass

    @abstractmethod
    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Troca o código de autorização temporário pelos tokens de acesso e id.

        Args:
            code: Código de autorização recebido via callback do provedor.

        Returns:
            dict[str, Any]: Dicionário contendo access_token, id_token e metadados.

        Raises:
            OAuthError: Caso o provedor recuse o código ou retorne erro HTTP.
        """
        pass

    @abstractmethod
    async def fetch_user_info(self, access_token: str) -> OAuthUserInfo:
        """Recupera os dados de perfil do usuário utilizando o token de acesso.

        Args:
            access_token: Token de acesso emitido pelo provedor OAuth.

        Returns:
            OAuthUserInfo: Estrutura tipada com os dados canônicos do usuário.

        Raises:
            OAuthError: Caso ocorra falha na requisição ao endpoint de userinfo.
        """
        pass
