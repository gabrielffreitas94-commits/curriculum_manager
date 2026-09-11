"""Schemas Pydantic para transferência de dados de usuários e configurações."""

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserSyncRequest(BaseModel):
    """Payload de entrada opcional para sincronização de usuário pós-login no Firebase.

    Attributes:
        target_title: Cargo profissional primariamente almejado.
        phone: Telefone de contato.
        location: Localidade de residência.
        preferred_language: Idioma preferencial da interface ('pt-BR', 'en-US', etc.).
    """

    target_title: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    location: str | None = Field(default=None, max_length=100)
    preferred_language: str | None = Field(default="pt-BR", max_length=10)


class UserSettingsResponse(BaseModel):
    """Representação serializada das configurações do usuário.

    Attributes:
        preferred_language: Código do idioma padrão selecionado na UI.
        has_gemini_key: Flag indicando se o usuário cadastrou sua API key do Gemini.
        email_notifications_enabled: Flag de preferência para recebimento de e-mails.
        in_app_notifications_enabled: Flag para exibição de alertas no dashboard.
        default_prompt_skill_id: UUID do template de prompt favorito do usuário.
    """

    model_config = ConfigDict(from_attributes=True)

    preferred_language: str
    has_gemini_key: bool
    email_notifications_enabled: bool
    in_app_notifications_enabled: bool
    default_prompt_skill_id: uuid.UUID | None = None


class UserResponse(BaseModel):
    """Representação pública do perfil do usuário autenticado.

    Attributes:
        id: Identificador único interno (UUID v4).
        firebase_uid: Identificador fornecido pelo Firebase Auth.
        email: E-mail cadastrado.
        full_name: Nome completo do usuário.
        phone: Telefone de contato ou None.
        location: Localidade cadastrada ou None.
        target_title: Cargo pretendido ou None.
        is_active: Status de ativação da conta.
        settings: Objeto de configurações associadas do usuário.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firebase_uid: str
    email: EmailStr
    full_name: str
    phone: str | None = None
    location: str | None = None
    target_title: str | None = None
    is_active: bool
    settings: UserSettingsResponse | None = None


class UserSettingsUpdateRequest(BaseModel):
    """Payload para atualização de configurações e chaves de IA do usuário.

    Attributes:
        gemini_api_key: Chave de API Google Gemini em texto plano para ser cifrada.
        preferred_language: Código do novo idioma padrão.
        email_notifications_enabled: Ativação/desativação de e-mails.
        in_app_notifications_enabled: Ativação/desativação de alertas no dashboard.
        default_prompt_skill_id: UUID do novo template de prompt favorito.
    """

    gemini_api_key: str | None = Field(default=None, max_length=255)
    preferred_language: str | None = Field(default=None, max_length=10)
    email_notifications_enabled: bool | None = None
    in_app_notifications_enabled: bool | None = None
    default_prompt_skill_id: uuid.UUID | None = None
