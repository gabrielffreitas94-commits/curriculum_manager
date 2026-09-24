"""Serviço de aplicação para autenticação de usuários e gestão de sessões Web."""

import time

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.models import User, UserSettings
from app.ports.auth_port import AuthPort, AuthUser
from app.ports.oauth_port import OAuthError, OAuthPort, OAuthUserInfo

logger = get_logger("auth_service")


class AuthService:
    """Gerencia casos de uso de autenticação, persistência de usuários e tokens de sessão.

    Attributes:
        _db: Sessão assíncrona com o banco relacional.
        _auth_port: Porta opcional para validação de tokens Bearer/Firebase.
        _secret_key: Chave secreta simétrica para assinatura de tokens JWT de sessão.
    """

    def __init__(
        self,
        db: AsyncSession,
        auth_port: AuthPort | None = None,
        secret_key: str | None = None,
    ) -> None:
        """Inicializa o serviço de autenticação injetando dependências.

        Args:
            db: Sessão transacional assíncrona do SQLAlchemy.
            auth_port: Adaptador de autenticação opcional para validação legacy/mock.
            secret_key: Chave secreta de assinatura JWT (padrão: settings.SECRET_KEY).
        """
        self._db = db
        self._auth_port = auth_port
        self._secret_key = secret_key or settings.SECRET_KEY

    def create_session_jwt(self, uid: str, email: str) -> str:
        """Emite um token JWT de sessão assinado para persistência em cookie HTTP.

        Args:
            uid: Identificador universal do usuário (Firebase UID ou google_{sub}).
            email: E-mail primário do usuário autenticado.

        Returns:
            str: Token JWT assinado contendo claims essenciais de sessão.
        """
        now = int(time.time())
        payload = {
            "sub": uid,
            "email": email,
            "iat": now,
            "exp": now + (86400 * 7),
            "iss": "thothcvs-web",
        }
        return jwt.encode(payload, self._secret_key, algorithm="HS256")

    async def get_authenticated_user(self, session_token: str | None) -> User | None:
        """Resolve e recupera a entidade User a partir do cookie de sessão.

        Executa duas etapas de resolução:
        1. Validação do JWT de sessão assinado com a SECRET_KEY do servidor.
        2. Fallback para validação de token via AuthPort (ex: Firebase / Bearer).

        Args:
            session_token: Valor do cookie session_token recebido na requisição.

        Returns:
            User | None: Usuário encontrado com configurações carregadas ou None se inválido.
        """
        if not session_token or not session_token.strip():
            return None

        # 1. Tenta decodificar como JWT de sessão próprio
        try:
            payload = jwt.decode(
                session_token,
                self._secret_key,
                algorithms=["HS256"],
                issuer="thothcvs-web",
            )
            sub = payload.get("sub")
            if sub:
                result = await self._db.execute(
                    select(User)
                    .options(selectinload(User.settings))
                    .where(User.firebase_uid == sub, User.deleted_at.is_(None))
                )
                user = result.scalar_one_or_none()
                if user:
                    return user
        except Exception:
            pass

        # 2. Fallback para AuthPort caso configurado (validação de token externo)
        if self._auth_port is not None:
            try:
                auth_user: AuthUser = await self._auth_port.verify_token(session_token)
                result = await self._db.execute(
                    select(User)
                    .options(selectinload(User.settings))
                    .where(User.firebase_uid == auth_user.uid, User.deleted_at.is_(None))
                )
                return result.scalar_one_or_none()
            except Exception:
                return None

        return None

    async def authenticate_oauth_user(self, oauth_port: OAuthPort, code: str) -> tuple[User, str]:
        """Orquestra o fluxo de autenticação OAuth 2.0.

        1. Troca o código temporário por tokens de acesso junto à porta do provedor.
        2. Recupera os dados canônicos do perfil do usuário via porta.
        3. Localiza ou provisiona o usuário no banco relacional e inicializa UserSettings.
        4. Emite e retorna o cookie de sessão JWT assinado.

        Args:
            oauth_port: Porta abstrata do provedor OAuth (Google, LinkedIn, etc.).
            code: Código de autorização retornado pelo provedor.

        Returns:
            tuple[User, str]: Tupla contendo o usuário autenticado e o token de sessão JWT.

        Raises:
            OAuthError: Caso a troca de código ou recuperação de perfil falhem.
        """
        tokens = await oauth_port.exchange_code(code)
        access_token = tokens.get("access_token")
        if not access_token:
            logger.error("oauth_access_token_missing_in_response")
            raise OAuthError("Token de acesso ausente na resposta do provedor OAuth.")

        user_info: OAuthUserInfo = await oauth_port.fetch_user_info(access_token)
        firebase_uid = f"google_{user_info.sub}"

        result = await self._db.execute(
            select(User).where(
                (User.firebase_uid == firebase_uid) | (User.email == user_info.email),
                User.deleted_at.is_(None),
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                firebase_uid=firebase_uid,
                email=user_info.email,
                full_name=user_info.full_name,
                is_active=True,
            )
            self._db.add(user)
            await self._db.flush()

            settings_entry = UserSettings(
                user_id=user.id,
                preferred_language="pt-BR",
                email_notifications_enabled=True,
                in_app_notifications_enabled=True,
            )
            self._db.add(settings_entry)
            await self._db.commit()
            logger.info(
                "user_provisioned",
                user_id=str(user.id),
                action="signup",
                auth_provider="google",
            )
        else:
            if not user.firebase_uid:
                user.firebase_uid = firebase_uid
            if user_info.full_name and not user.full_name:
                user.full_name = user_info.full_name
            await self._db.commit()
            logger.info(
                "user_authenticated",
                user_id=str(user.id),
                action="login",
                auth_provider="google",
            )

        session_token = self.create_session_jwt(uid=user.firebase_uid, email=user.email)
        return user, session_token
