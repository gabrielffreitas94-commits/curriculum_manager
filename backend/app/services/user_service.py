"""Serviço de aplicação para gestão do ciclo de vida de usuários (Hexagonal Architecture).

Implementa operações atômicas de conformidade com a LGPD (Lei Geral de Proteção de Dados - Art. 18),
especificamente o Direito à Eliminação dos dados pessoais tratados com consentimento do titular.
"""

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PromptSkill, User
from app.ports.auth_port import AuthPort


class UserService:
    """Serviço responsável por regras de negócio e ciclo de vida de contas de usuários."""

    def __init__(self, db: AsyncSession, auth_port: AuthPort) -> None:
        """Inicializa o serviço de usuários com a sessão de banco e a porta de autenticação.

        Args:
            db: Sessão assíncrona do SQLAlchemy.
            auth_port: Porta de autenticação e gestão de identidade.
        """
        self.db = db
        self.auth_port = auth_port

    async def delete_user_account(self, user: User) -> None:
        """Executa a eliminação definitiva de todos os dados do usuário (LGPD Art. 18, VI).

        Remove o usuário e, em cascata atômica transacional:
        - Configurações e preferências (UserSettings, chaves criptografadas de API)
        - Dossiê factual completo (experiências, educações, certificações, competências)
        - Histórico de candidaturas ATS (applications, stages, contacts, notes)
        - Documentos sintetizados (generated_resumes, cover_letters)
        - Notificações de sistema e lembretes
        - PromptSkills customizadas criadas pelo usuário (não pertencentes ao sistema padrão)

        Ao final da transação, revoga os tokens e sessões do usuário no provedor de autenticação.

        Args:
            user: Usuário autenticado requerente da exclusão.
        """
        firebase_uid = user.firebase_uid
        user_id = user.id

        # 1. Remove PromptSkills customizadas criadas pelo usuário
        await self.db.execute(
            delete(PromptSkill).where(
                PromptSkill.created_by_user_id == user_id,
                PromptSkill.is_system_default.is_(False),
            )
        )

        # 2. Deleta a entidade User (cascade='all, delete-orphan' limpa tabelas filhas)
        await self.db.delete(user)
        await self.db.commit()

        # 3. Revoga tokens ativos no provedor de identidade
        await self.auth_port.revoke_user_tokens(firebase_uid)
