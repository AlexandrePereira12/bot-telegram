"""Registro de todos os modelos.

Importar este pacote garante que o metadata do SQLAlchemy conheca todas as
tabelas — necessario para o autogenerate do Alembic e para create_all nos
testes.
"""

from app.models.campaign import Ad, AdSet, Campaign, TrackingToken
from app.models.content import FunnelContent, QualificationOption
from app.models.conversation import Conversation, Message
from app.models.conversion import AuditLog, ConsentRecord, Conversion, IdempotencyKey
from app.models.lead import Event, Lead
from app.models.operator import Operator
from app.models.telegram_user import TelegramUser

__all__ = [
    "Ad",
    "AdSet",
    "AuditLog",
    "Campaign",
    "ConsentRecord",
    "Conversation",
    "Conversion",
    "Event",
    "FunnelContent",
    "IdempotencyKey",
    "Lead",
    "Message",
    "Operator",
    "QualificationOption",
    "TelegramUser",
    "TrackingToken",
]
