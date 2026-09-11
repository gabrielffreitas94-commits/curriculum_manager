"""Schemas Pydantic para o sistema de notificações e lembretes in-app do ATS.

Define modelos para listagem, contagem de pendências e respostas de ações em lote.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    """Representação serializada de notificação in-app."""

    id: uuid.UUID
    application_id: uuid.UUID | None = None
    notification_type: str
    title: str
    message: str
    is_read: bool
    scheduled_for: datetime
    sent_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UnreadCountResponse(BaseModel):
    """Contagem total de notificações pendentes de leitura."""

    unread_count: int


class BatchUpdateResponse(BaseModel):
    """Resultado da execução de operações em lote sobre notificações."""

    updated_count: int


class ScanFollowUpsResponse(BaseModel):
    """Resultado da varredura algorítmica de lembretes de follow-up."""

    created_count: int
