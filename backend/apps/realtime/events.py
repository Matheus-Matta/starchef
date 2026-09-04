from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone


def account_group(account_id):
    return f"realtime_a{str(account_id).replace('-', '')}"


def broadcast_model_event(account_id, event, payload):
    channel_layer = get_channel_layer()
    if not channel_layer or not account_id:
        return
    async_to_sync(channel_layer.group_send)(
        account_group(account_id),
        {"type": "realtime.event", "event": event, "payload": payload},
    )


def broadcast_resource_event(
    account_id,
    *,
    resource,
    action,
    restaurant_id=None,
    branch_id=None,
    changed_fields=(),
):
    """Publica uma invalidação compacta para operações ORM em lote.

    ``bulk_create`` e ``QuerySet.update`` não executam ``save`` e, portanto,
    não passam pelos signals. Um evento de coleção é suficiente para o PDV
    reler o recurso autenticado sem gerar uma rajada por registro.
    """
    broadcast_model_event(
        account_id,
        f"model.{action}",
        {
            "resource": resource,
            "model": resource.rsplit(".", 1)[-1],
            "action": action,
            "id": "",
            "branch_id": str(branch_id or ""),
            "restaurant_id": str(restaurant_id or ""),
            "changed_fields": sorted(changed_fields),
            "occurred_at": timezone.now().isoformat(),
            "protocol_version": 1,
        },
    )
