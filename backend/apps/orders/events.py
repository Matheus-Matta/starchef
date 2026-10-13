from apps.realtime import envio_em_lote


def compact_id(value):
    return str(value).replace("-", "")


def kitchen_group(account_id, branch_id, sector):
    return f"k_a{compact_id(account_id)}_b{compact_id(branch_id)}_s{sector}"


def broadcast_kitchen_event(account_id, branch_id, sector, event_type, payload):
    # Em lote dentro da requisição: uma conexão para todos (`envio_em_lote`).
    envio_em_lote.enviar(
        kitchen_group(account_id, branch_id, sector),
        {
            "type": "kitchen.event",
            "event": event_type,
            "payload": payload,
        },
    )
