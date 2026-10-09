"""Fechar conta de comanda é da LOJA enquanto ela está no ar.

A comanda cobrada nos dois servidores ao mesmo tempo é dinheiro em dobro: um
caixa fechou o cartão na loja e, um minuto depois, outro — ainda grudado na
nuvem pela janela do veredito — fechou o MESMO cartão lá, antes de a primeira
cobrança chegar pela sincronização (simulação do dia a dia,
`loadtest/dia_a_dia`: R$ 495,17 na loja e R$ 505,17 na nuvem).

A nuvem só cobra comanda quando a loja está FORA: sem sinal de vida do
`sync_worker` dela (o pulso é a cada 20 s) há mais de [JANELA]. Com a loja no
ar, a nuvem recusa com 409 `cobrar_na_loja` e o PDV volta para a loja.

A recusa vale SÓ para o PDV que veio pela janela do veredito sem tentar a
loja agora (`X-Desvio-Da-Loja: janela`). O terminal configurado direto na
nuvem, ou que acabou de ver a loja falhar, cobra na nuvem: o sinal de vida é
do `sync_worker`, não prova que o PDV alcança a loja, e recusar todo mundo
deixava a comanda sem fechar em lugar nenhum (v3.0.86: "não consigo finalizar
pedido com comanda"). Fechar comanda (`attach-commands`) o PDV sempre tenta na
loja primeiro — é lá que mora a proteção contra cobrar duas vezes.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.synchronization.constants import NodeType
from apps.synchronization.services import guard, nodes

JANELA = timedelta(seconds=60)
CODIGO = "cobrar_na_loja"
MENSAGEM = ("A loja está no ar: feche a conta da comanda pelo servidor da loja. "
            "Na nuvem a mesma comanda poderia ser cobrada duas vezes.")


def recusar_fechamento(request, restaurante):
    """A nuvem deve mandar ESTE fechamento de comanda para a loja?"""
    if request.headers.get("X-Desvio-Da-Loja") != "janela":
        return False
    return loja_no_ar(restaurante)


def loja_no_ar(restaurante):
    """Na NUVEM: o nó da loja deste restaurante deu sinal há pouco?"""
    if not guard.is_enabled() or not nodes.is_cloud():
        return False
    from apps.synchronization.models import SyncNode

    return SyncNode.objects.filter(
        Q(restaurant_id=restaurante.pk) | Q(restaurant__isnull=True),
        account_id=restaurante.account_id, node_type=NodeType.LOCAL, is_active=True,
        last_seen_at__gte=timezone.now() - JANELA,
    ).exists()
