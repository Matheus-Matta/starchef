"""Serviços de notificação (criação + entrega em tempo real via WebSocket).

Fornece duas formas de uso:

1. `notify(...)` — função direta para casos pontuais.
2. `NotificationType` — classe-base reutilizável: subclasses declaram
   `category`/`level` e implementam `build(**ctx)` e `recipients(**ctx)`, e
   `dispatch(account=..., **ctx)` cria e envia para cada destinatário. Assim os
   tipos de notificação ficam padronizados e reaproveitáveis (ver `types.py`).
"""
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.notifications.events import broadcast_notification
from apps.notifications.models import Notification

MANAGER_PROFILE_TYPES = ("admin", "owner", "manager")


def serialize_notification(notification):
    """Representação usada tanto no payload do WS quanto (mesmo formato) na API."""
    return {
        "id": str(notification.id),
        "category": notification.category,
        "level": notification.level,
        "title": notification.title,
        "body": notification.body,
        "url": notification.url,
        "entity": notification.entity,
        "object_id": notification.object_id,
        "metadata": notification.metadata,
        "is_read": notification.is_read,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


def managers_of_account(account_id, exclude_user_id=None):
    """Usuários que podem tratar aprovações da conta (admin/owner/manager)."""
    User = get_user_model()
    queryset = User.objects.filter(
        is_active=True,
        profile__account_id=account_id,
        profile__profile_type__in=MANAGER_PROFILE_TYPES,
    )
    if exclude_user_id:
        queryset = queryset.exclude(pk=exclude_user_id)
    return queryset


def notify(
    recipients,
    *,
    account,
    category=Notification.CATEGORY_SYSTEM,
    level=Notification.LEVEL_INFO,
    title,
    body="",
    url="",
    entity="",
    object_id="",
    metadata=None,
):
    """Cria uma notificação por destinatário e agenda a entrega via WS no commit.

    A entrega ocorre em `transaction.on_commit` para não emitir eventos de uma
    transação que ainda pode sofrer rollback.
    """
    users = [u for u in recipients if u is not None]
    if not users:
        return []

    created = [
        Notification.all_objects.create(
            account=account,
            recipient=user,
            category=category,
            level=level,
            title=title,
            body=body,
            url=url,
            entity=entity,
            object_id=str(object_id or ""),
            metadata=metadata or {},
        )
        for user in users
    ]

    payloads = [(n.recipient_id, serialize_notification(n)) for n in created]

    def _deliver():
        for user_id, payload in payloads:
            broadcast_notification(user_id, payload)

    transaction.on_commit(_deliver)
    return created


class NotificationType:
    """Base reutilizável para definir um tipo de notificação.

    Subclasses definem `category`/`level` e implementam:
      - `build(**context) -> dict`  → {title, body, url?, entity?, object_id?, metadata?}
      - `recipients(**context)`     → iterável de usuários destinatários
    e chamam `dispatch(account=..., **context)`.
    """

    category = Notification.CATEGORY_SYSTEM
    level = Notification.LEVEL_INFO

    def build(self, **context):
        raise NotImplementedError

    def recipients(self, **context):
        raise NotImplementedError

    def dispatch(self, *, account, **context):
        data = self.build(**context)
        return notify(
            self.recipients(**context),
            account=account,
            category=self.category,
            level=self.level,
            **data,
        )
