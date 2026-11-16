"""Liberar rodadas vencidas a partir de uma LEITURA (KDS, fila de impressão).

Fora de `orders/services.py` para não engordá-lo; importa `services` só dentro
da função, porque `services` é carregado por quase tudo em `orders`.
"""
from django.core.cache import cache

#: De quanto em quanto tempo uma LEITURA (KDS, fila de impressão) pode liberar
#: rodadas vencidas, por conta.
LIBERACAO_NA_LEITURA_SEGUNDOS = 5


def liberar_rodadas_vencidas_na_leitura(account_id):
    """A rede de segurança da leitura, no máximo uma vez a cada poucos segundos.

    Quem libera a rodada agendada é o beat (`orders.dispatch_due_kitchen_batches`).
    As leituras do KDS e da fila de impressão também liberam, para o caso de
    o Celery estar parado — mas elas chegam várias vezes por segundo numa loja
    com algumas telas de KDS e PDVs, e cada uma refazia a varredura inteira.
    Uma por conta a cada `LIBERACAO_NA_LEITURA_SEGUNDOS` cobre o mesmo caso.

    Cache fora do ar não pode tirar a rede de segurança: libera assim mesmo.
    """
    from apps.orders.services import dispatch_due_kitchen_batches

    try:
        primeira = cache.add(f"orders:liberar-na-leitura:{account_id}", 1,
                             timeout=LIBERACAO_NA_LEITURA_SEGUNDOS)
    except Exception:  # noqa: BLE001 — Redis fora: melhor varrer do que não liberar
        primeira = True
    if not primeira:
        return 0
    return dispatch_due_kitchen_batches(account_id=account_id)
