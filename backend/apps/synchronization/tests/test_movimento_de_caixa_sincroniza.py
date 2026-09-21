"""O movimento de caixa MUDA de estado — e a nuvem precisa acompanhar.

`CashMovement` foi declarado `immutable=True` no catálogo, com o comentário
"movimento é imutável: a loja insere e nunca reescreve". A frase descreve um
livro-razão, e o model não é um: ele tem ciclo de vida.

    pending  ──(gerente aprova a sangria)──►  approved
    approved ──(recebimento cancelado)─────►  cancelled

Com `immutable=True` o destino INSERE e nunca atualiza, então as duas setas
acima morrem na chegada. O saldo é `Sum(amount)` sobre `status="approved"`, e o
resultado é aritmético: **a nuvem e a loja fecham o turno com valores
diferentes**, sempre para o mesmo lado.

Este arquivo mede as duas setas de ponta a ponta.
"""
from decimal import Decimal

import pytest

from apps.synchronization.constants import Direction, EventStatus, Operation
from apps.synchronization.models import SyncEvent
from apps.synchronization.services import apply, crypto, serialization
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db


def _envelope_da_loja(no_loja, instancia, **mudancas):
    """O payload que a LOJA mandaria depois de mexer na linha.

    As mudanças são aplicadas só na cópia em memória, e `updated_at` é
    empurrado para a frente: o teste roda num banco só, então a linha gravada
    faz o papel do que a NUVEM tem, e este payload faz o papel do que a loja
    acabou de gravar. Sem essa separação as duas versões são iguais e
    `conflicts.decide` manda IGNORAR — o teste passaria sem transportar nada.
    """
    from datetime import timedelta

    from django.utils import timezone

    for campo, valor in mudancas.items():
        setattr(instancia, campo, valor)
    instancia.updated_at = timezone.now() + timedelta(seconds=5)
    return serialization.build_payload(
        instancia, registry.require("cash_movement"), origin_node_id=no_loja.id
    )


def _entregar_payload(conta, origem, destino, payload, *, sequence):
    """Entrega um payload já montado, como a nuvem o receberia."""
    evento = SyncEvent.objects.create(
        account=conta, source_node=origem, target_node=destino,
        direction=Direction.INBOUND, sequence=sequence,
        entity_type=payload["entity_type"], entity_id=payload["entity_id"],
        operation=Operation.UPSERT, entity_version=payload["entity_version"],
        payload=payload, payload_checksum=crypto.checksum(payload),
        status=EventStatus.RECEIVED,
    )
    return apply.apply_event(evento)


@pytest.fixture
def gaveta(conta):
    """Uma sessão de caixa com um movimento de venda e uma sangria pendente."""
    from django.contrib.auth import get_user_model

    from apps.core.tenant import tenant_context
    from apps.payments.models import CashMovement, CashRegister, CashStation
    from apps.restaurants.models import Restaurant

    restaurante = Restaurant.objects.create(account=conta, legal_name="B LTDA", trade_name="B")
    operador = get_user_model().objects.create_user("caixa-sync", "c@t.test", "x")
    with tenant_context(conta):
        estacao = CashStation.objects.create(
            account=conta, restaurant=restaurante, name="Caixa 1"
        )
        sessao = CashRegister.objects.create(
            account=conta, restaurant=restaurante, cash_station=estacao,
            status=CashRegister.STATUS_OPEN, opened_by=operador,
        )
        venda = CashMovement.objects.create(
            account=conta, restaurant=restaurante, cash_register=sessao,
            operator=operador, movement_type=CashMovement.TYPE_SALE,
            amount=Decimal("100.00"), status="approved", reason="Venda em dinheiro",
        )
        sangria = CashMovement.objects.create(
            account=conta, restaurant=restaurante, cash_register=sessao,
            operator=operador, movement_type=CashMovement.TYPE_WITHDRAWAL,
            amount=Decimal("-40.00"), status="pending", reason="Sangria para o cofre",
        )
    return {
        "restaurante": restaurante, "estacao": estacao, "sessao": sessao,
        "venda": venda, "sangria": sangria, "operador": operador,
    }


def test_a_sangria_aprovada_pelo_gerente_chega_aprovada(
    como_nuvem, conta, no_loja, no_nuvem, gaveta,
):
    """O caso mais caro, e ele acontece todo dia.

    A sangria nasce `pending` e sincroniza assim. O gerente aprova; se a
    aprovação não viajar, a nuvem segue somando o saldo SEM a retirada — e o
    caixa da nuvem fica R$ 40 mais cheio que o da loja, para sempre.
    """
    from apps.payments.models import CashMovement

    # A linha gravada é o que a NUVEM tem: a sangria ainda pendente.
    assert CashMovement.all_objects.get(pk=gaveta["sangria"].pk).status == "pending"

    # Na loja, o gerente aprovou.
    payload = _envelope_da_loja(no_loja, gaveta["sangria"], status="approved")
    assert _entregar_payload(conta, no_loja, no_nuvem, payload, sequence=10) is True

    assert CashMovement.all_objects.get(pk=gaveta["sangria"].pk).status == "approved", (
        "a aprovação da sangria não chegou: o saldo da nuvem vai divergir do "
        "da loja pelo valor da retirada"
    )


def test_o_movimento_cancelado_chega_cancelado(
    como_nuvem, conta, no_loja, no_nuvem, gaveta,
):
    """Estornar uma venda em dinheiro tira o valor da gaveta.

    Se o cancelamento não viaja, a nuvem continua contando a venda desfeita.
    """
    from apps.payments.models import CashMovement

    payload = _envelope_da_loja(no_loja, gaveta["venda"], status="cancelled")
    assert _entregar_payload(conta, no_loja, no_nuvem, payload, sequence=10) is True

    assert CashMovement.all_objects.get(pk=gaveta["venda"].pk).status == "cancelled", (
        "o cancelamento não chegou: a nuvem segue somando uma venda estornada"
    )


def test_o_saldo_da_nuvem_passa_a_bater_com_o_da_loja(
    como_nuvem, conta, no_loja, no_nuvem, gaveta,
):
    """A consequência, em reais.

    Gaveta: venda +100, sangria -40 pendente. Depois de o gerente aprovar, a
    loja espera 60. Se a aprovação não viajar, a nuvem soma só a venda e diz
    100 — quarenta reais de diferença numa conferência de turno.
    """
    from django.db.models import Sum

    from apps.payments.models import CashMovement

    payload = _envelope_da_loja(no_loja, gaveta["sangria"], status="approved")
    _entregar_payload(conta, no_loja, no_nuvem, payload, sequence=10)

    saldo = CashMovement.all_objects.filter(
        cash_register_id=gaveta["sessao"].pk, status="approved"
    ).aggregate(valor=Sum("amount"))["valor"]
    assert saldo == Decimal("60.00"), (
        f"a nuvem fecharia o turno com {saldo} em vez de 60,00"
    )


def test_evento_velho_nao_reescreve_o_movimento(
    como_nuvem, conta, no_loja, no_nuvem, gaveta,
):
    """A proteção que substitui o `immutable`.

    Tirar `immutable=True` não abre a porta para qualquer reescrita: a
    resolução de conflito IGNORA versão anterior à local. É isso que impede um
    evento atrasado de ressuscitar um movimento já cancelado.
    """
    from apps.payments.models import CashMovement

    # O envelope ANTIGO é montado primeiro, ainda dizendo "approved".
    velho = serialization.build_payload(
        CashMovement.all_objects.get(pk=gaveta["venda"].pk),
        registry.require("cash_movement"),
        origin_node_id=no_loja.id,
    )

    novo = _envelope_da_loja(no_loja, gaveta["venda"], status="cancelled")
    assert _entregar_payload(conta, no_loja, no_nuvem, novo, sequence=10) is True

    # Agora o atrasado chega, dizendo que a venda ainda vale.
    _entregar_payload(conta, no_loja, no_nuvem, velho, sequence=11)

    assert CashMovement.all_objects.get(pk=gaveta["venda"].pk).status == "cancelled", (
        "um evento atrasado ressuscitou um movimento cancelado"
    )


def test_o_movimento_continua_subindo_so_da_loja():
    """Mão única: a nuvem nunca empurra movimento de caixa para baixo.

    É metade da razão de tirar o `immutable` ser seguro — a outra metade é a
    ordem de versão, provada acima.
    """
    entrada = registry.require("cash_movement")
    assert entrada.flow == "local_to_cloud"
    assert not entrada.immutable, (
        "o movimento de caixa tem ciclo de vida (pending → approved → "
        "cancelled); declará-lo append-only faz a nuvem parar na primeira etapa"
    )
