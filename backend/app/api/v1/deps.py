"""Dependências injetáveis do FastAPI para autenticação, sessão de banco e autorização.

Implementa o isolamento de tenant e a verificação do ID Token do Firebase
para proteger todas as rotas privadas do ThothCVs AI.
"""

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.firebase_auth_adapter import FirebaseAuthAdapter
from app.adapters.google_oauth_adapter import GoogleOAuthAdapter
from app.core.database import get_db_session
from app.domain.models import User
from app.ports.auth_port import AuthError, AuthUser, InvalidTokenError
from app.ports.oauth_port import OAuthPort

if TYPE_CHECKING:
    from app.services.document_service import DocumentService
    from app.services.user_service import UserService

# Instâncias dos adaptadores de autenticação
auth_adapter = FirebaseAuthAdapter()
google_oauth_adapter: OAuthPort = GoogleOAuthAdapter()

# Esquema de extração do Bearer Token
security = HTTPBearer(auto_error=True)


async def get_current_auth_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthUser:
    """Extrai e valida o token Bearer do cabeçalho HTTP Authorization.

    Args:
        credentials: Objeto de credenciais HTTP injetado automaticamente.

    Returns:
        AuthUser: Entidade de usuário autenticado validada pelo Firebase.

    Raises:
        HTTPException: Status 401 caso o token seja inválido, ausente ou expirado.
    """
    token = credentials.credentials
    try:
        return await auth_adapter.verify_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Credencial de autenticação inválida ou expirada: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Falha de autenticação: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_user(
    auth_user: AuthUser = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """Consulta o usuário no banco relacional associado ao UID Firebase do token.

    Garante o isolamento de tenant verificando `deleted_at IS NULL`.

    Args:
        auth_user: Dados do usuário autenticado no Firebase.
        db: Sessão transacional assíncrona do banco de dados.

    Returns:
        User: Instância gerenciada do modelo relacional do usuário.

    Raises:
        HTTPException: Status 404 caso o usuário ainda não tenha sido sincronizado via /sync.
    """
    result = await db.execute(
        select(User)
        .options(selectinload(User.settings))
        .where(User.firebase_uid == auth_user.uid, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário autenticado não encontrado no banco de dados. Realize a sincronização.",
        )

    return user


async def get_document_service(
    db: AsyncSession = Depends(get_db_session),
) -> "DocumentService":
    """Injeta uma instância ativa de DocumentService com a sessão de banco do request.

    Args:
        db: Sessão de banco de dados ativa.

    Returns:
        DocumentService pronto para uso.
    """
    from app.services.document_service import DocumentService

    return DocumentService(db=db)


async def get_user_service(
    db: AsyncSession = Depends(get_db_session),
) -> "UserService":
    """Injeta uma instância ativa de UserService com a sessão de banco do request.

    Args:
        db: Sessão de banco de dados ativa.

    Returns:
        UserService pronto para uso.
    """
    from app.services.user_service import UserService

    return UserService(db=db, auth_port=auth_adapter)
