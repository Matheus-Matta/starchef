from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


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

