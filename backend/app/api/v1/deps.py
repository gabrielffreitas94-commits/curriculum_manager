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
    from app.ports.resume_parser_port import ResumeParserPort
    from app.services.auth_service import AuthService
    from app.services.copilot_service import CopilotService
    from app.services.document_service import DocumentService
    from app.services.job_ingest_service import JobIngestService
    from app.services.profile_service import ProfileService
    from app.services.prompt_skill_service import PromptSkillService
    from app.services.resume_service import ResumeService
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


async def get_auth_service(
    db: AsyncSession = Depends(get_db_session),
) -> "AuthService":
    """Injeta uma instância ativa de AuthService com a sessão de banco do request.

    Args:
        db: Sessão de banco de dados ativa.

    Returns:
        AuthService pronto para uso.
    """
    from app.services.auth_service import AuthService

    return AuthService(db=db, auth_port=auth_adapter)


async def get_profile_service(
    db: AsyncSession = Depends(get_db_session),
) -> "ProfileService":
    """Injeta uma instância ativa de ProfileService com a sessão de banco do request.

    Args:
        db: Sessão de banco de dados ativa.

    Returns:
        ProfileService pronto para uso.
    """
    from app.services.profile_service import ProfileService

    return ProfileService(db=db)


def resolve_gemini_api_key(user: User | None = None) -> str | None:
    """Resolve a chave de API do Gemini a partir das configurações do usuário ou ambiente.

    Args:
        user: Instância opcional do usuário autenticado.

    Returns:
        str | None: Chave do Gemini decifrada ou obtida do ambiente.
    """
    import os

    from app.core.crypto import crypto_service

    if user and user.settings and user.settings.encrypted_gemini_api_key:
        try:
            user_associated_data = str(user.id).encode("utf-8")
            return crypto_service.decrypt(
                user.settings.encrypted_gemini_api_key,
                associated_data=user_associated_data,
            )
        except Exception:
            try:
                return crypto_service.decrypt(user.settings.encrypted_gemini_api_key)
            except Exception:
                pass
    return os.getenv("GEMINI_API_KEY")


def get_resume_parser_adapter(api_key: str | None = None) -> "ResumeParserPort":
    """Instancia o adaptador concreto de parsing de currículos.

    Args:
        api_key: Chave do Gemini decifrada ou default.

    Returns:
        ResumeParserPort: Instância do adaptador de parsing.
    """
    from app.adapters.gemini_resume_parser_adapter import GeminiResumeParserAdapter

    return GeminiResumeParserAdapter(api_key=api_key)


async def get_prompt_skill_service(
    db: AsyncSession = Depends(get_db_session),
) -> "PromptSkillService":
    """Injeta uma instância ativa de PromptSkillService com a sessão do banco.

    Args:
        db: Sessão ativa do banco de dados relacional.

    Returns:
        PromptSkillService pronto para uso.
    """
    from app.services.prompt_skill_service import PromptSkillService

    return PromptSkillService(db=db)


def get_job_ingest_service() -> "JobIngestService":
    """Injeta uma instância ativa de JobIngestService.

    Returns:
        JobIngestService pronto para ingestão de vagas.
    """
    from app.services.job_ingest_service import JobIngestService

    return JobIngestService()


async def get_copilot_service(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> "CopilotService":
    """Injeta uma instância de CopilotService configurada com o adaptador de IA do usuário.

    Args:
        db: Sessão ativa do banco de dados relacional.
        current_user: Usuário autenticado proprietário.

    Returns:
        CopilotService pronto para interações conversacionais.
    """
    from app.adapters.gemini_ai_adapter import GeminiAIAdapter
    from app.services.copilot_service import CopilotService

    api_key = resolve_gemini_api_key(current_user)
    ai_adapter = GeminiAIAdapter(api_key=api_key)
    return CopilotService(db=db, ai_port=ai_adapter)


def create_copilot_service(db: AsyncSession, user: User) -> "CopilotService":
    """Cria uma instância de CopilotService para um usuário específico.

    Args:
        db: Sessão ativa do banco de dados relacional.
        user: Usuário autenticado proprietário.

    Returns:
        CopilotService configurado.
    """
    from app.adapters.gemini_ai_adapter import GeminiAIAdapter
    from app.services.copilot_service import CopilotService

    api_key = resolve_gemini_api_key(user)
    ai_adapter = GeminiAIAdapter(api_key=api_key)
    return CopilotService(db=db, ai_port=ai_adapter)


async def get_resume_service(
    db: AsyncSession = Depends(get_db_session),
) -> "ResumeService":
    """Injeta uma instância ativa de ResumeService com a sessão do banco.

    Args:
        db: Sessão ativa do banco de dados relacional.

    Returns:
        ResumeService pronto para síntese e análise de currículos.
    """
    from app.services.resume_service import ResumeService

    return ResumeService(db=db)
