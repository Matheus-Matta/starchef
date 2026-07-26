from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def compact_id(value):
    return str(value).replace("-", "")


def notification_group(user_id):
    """Grupo do Channels por usuário destinatário."""
    return f"notif_u{compact_id(user_id)}"


def broadcast_notification(user_id, payload):
    """Envia uma notificação serializada ao grupo WS do usuário."""
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    async_to_sync(channel_layer.group_send)(
        notification_group(user_id),
        {"type": "notification.message", "payload": payload},
    )
