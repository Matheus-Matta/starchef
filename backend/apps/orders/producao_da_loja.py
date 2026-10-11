"""Quem libera a rodada agendada da cozinha: quem tem a cozinha.

Impressora e KDS ficam na loja. Com servidor de loja, a nuvem NÃO libera rodada
nenhuma da conta: liberando uma rodada que a loja já tinha liberado (o
"liberada" vinha atrás na sincronização), a nuvem salvava o pedido e gerava
uma versão nova dele — de antes de o pagamento chegar lá — que desfazia o
pagamento na loja. Conta só-nuvem (sem servidor de loja) libera na nuvem.

E rodada IMEDIATA (sem carência) já sai liberada na criação: encontrada
"agendada" por uma tarefa, é só a sincronização atrasada, nunca trabalho a fazer.
"""
from django.db.models import F


def contas_da_loja():
    """Contas cuja cozinha é da loja — vazio fora da nuvem."""
    from apps.synchronization.services import guard, nodes

    if not guard.is_enabled() or not nodes.is_cloud():
        return set()
    from apps.synchronization.constants import NodeType
    from apps.synchronization.models import SyncNode

    return set(SyncNode.objects.filter(node_type=NodeType.LOCAL, is_active=True)
               .values_list("account_id", flat=True))


def a_liberar_aqui(rodadas):
    """Das rodadas agendadas e vencidas, as que ESTE servidor deve liberar."""
    # Imediata = liberada no MESMO instante do envio (os dois campos recebem o
    # mesmo valor na criação). Só ela fica de fora; a com carência entra.
    return rodadas.exclude(dispatch_at=F("sent_at")).exclude(account_id__in=contas_da_loja())
