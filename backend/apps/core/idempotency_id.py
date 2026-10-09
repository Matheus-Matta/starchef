"""O id da chave de idempotência, igual em qualquer nó.

`uuid5(conta:chave)`: a mesma operação tentada na loja e na nuvem gera o mesmo
id nos dois bancos, e a sincronização leva a chave de um ao outro sem colidir.
"""
import uuid

#: Namespace fixo. NUNCA muda: mudar daria a uma operação já gravada um id
#: diferente do que o outro nó conhece. A migração `core/0002` usa o mesmo.
IDEMPOTENCY_NAMESPACE = uuid.UUID("6f1d5c2e-8a4b-4c3e-9b7a-2d1e0f3c4b5a")


def idempotency_record_id(account_id, key):
    return uuid.uuid5(IDEMPOTENCY_NAMESPACE, f"{account_id}:{key}")
