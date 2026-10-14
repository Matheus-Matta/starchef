"""Tirar, no CAIXA, um item da comanda na hora de cobrar — fora do prazo.

Na hora do pagamento o cliente confere a conta em voz alta: "esse refri não é
meu". A comanda foi lida no PDV e o item veio junto, mas a janela de
cancelamento do restaurante (`item_cancel_window_seconds`, os "3 minutos")
já tinha passado havia muito — e o caixa não tinha como tirar o item sem
chamar alguém com a senha.

A janela existe para o SALÃO não sumir com prato já feito. No caixa, com a
sessão aberta e o cliente na frente, quem tira o item é quem está cobrando, e
o motivo e o autor ficam gravados. Por isso a liberação vale só com
`checkout=true` E com caixa aberto por quem pede: o app do garçom não manda o
sinal, e mandar o sinal sem caixa aberto não adianta.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import AuditLog
from apps.orders.command_items import launch_item
from apps.orders.models import CommandItem
from apps.payments.services import open_cash_register
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


@pytest.fixture
def anotacao_fora_do_prazo(contexto_tenant, account, restaurant, branch, manager_user, produto):
    restaurant.item_cancel_window_seconds = 180
    restaurant.save(update_fields=["item_cancel_window_seconds"])
    comanda = Command.objects.create(account=account, restaurant=restaurant, branch=branch, number=52)
    anotacao = launch_item(command=comanda, product=produto, user=manager_user, quantity=1)
    CommandItem.all_objects.filter(pk=anotacao.pk).update(
        status=CommandItem.STATUS_SENT,
        sent_to_kitchen_at=timezone.now() - timedelta(minutes=20),
    )
    return comanda, anotacao


@pytest.fixture
def caixa_aberto(contexto_tenant, restaurant, branch, manager_user):
    return open_cash_register(
        restaurant=restaurant, branch=branch, user=manager_user, opening_amount=Decimal("0.00")
    )


def _remover(cliente, comanda, anotacao, **extra):
    return cliente.delete(
        f"/api/v1/commands/{comanda.pk}/items/{anotacao.pk}/void/",
        {"reason": "Cliente disse que não pediu", **extra},
        format="json",
    )


def test_caixa_aberto_remove_item_da_comanda_fora_do_prazo(api_client, anotacao_fora_do_prazo, caixa_aberto):
    comanda, anotacao = anotacao_fora_do_prazo

    resposta = _remover(api_client, comanda, anotacao, checkout=True)

    assert resposta.status_code == 204, resposta.content
    anotacao.refresh_from_db()
    assert anotacao.status == CommandItem.STATUS_CANCELLED
    assert anotacao.void_reason == "Cliente disse que não pediu"


def test_a_remocao_no_caixa_fica_registrada_como_liberada_pelo_caixa(
    api_client, anotacao_fora_do_prazo, caixa_aberto
):
    """Sem senha não há "quem autorizou": o registro precisa dizer por onde passou."""
    comanda, anotacao = anotacao_fora_do_prazo

    _remover(api_client, comanda, anotacao, checkout=True)

    registro = AuditLog.all_objects.filter(metadata__event="command_item_voided").latest("created_at")
    assert registro.metadata.get("released_at_checkout") is True


def test_sem_caixa_aberto_o_sinal_do_caixa_nao_libera(api_client, anotacao_fora_do_prazo):
    """Qualquer cliente pode mandar `checkout=true`; quem decide é o caixa aberto."""
    comanda, anotacao = anotacao_fora_do_prazo

    resposta = _remover(api_client, comanda, anotacao, checkout=True)

    assert resposta.status_code == 409, resposta.content
    anotacao.refresh_from_db()
    assert anotacao.status == CommandItem.STATUS_SENT


def test_fora_do_caixa_o_prazo_continua_valendo(api_client, anotacao_fora_do_prazo, caixa_aberto):
    """O app do garçom não manda o sinal: o salão segue preso à janela."""
    comanda, anotacao = anotacao_fora_do_prazo

    resposta = _remover(api_client, comanda, anotacao)

    assert resposta.status_code == 409, resposta.content
    anotacao.refresh_from_db()
    assert anotacao.status == CommandItem.STATUS_SENT
