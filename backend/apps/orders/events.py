from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def compact_id(value):
    return str(value).replace("-", "")


def kitchen_group(account_id, branch_id, sector):
    return f"k_a{compact_id(account_id)}_b{compact_id(branch_id)}_s{sector}"


def broadcast_kitchen_event(account_id, branch_id, sector, event_type, payload):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    async_to_sync(channel_layer.group_send)(
        kitchen_group(account_id, branch_id, sector),
        {
            "type": "kitchen.event",
            "event": event_type,
            "payload": payload,
        },
    )
