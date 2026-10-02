"""Zerar comandas em lote: retirar o que está aberto, guardar o histórico, liberar.

Fim do dia, ou depois de um pico como o de 01/10: cartões com anotação esquecida
ficam "ocupados" e o operador precisava abrir um por um e cancelar item a item.

Zerar não apaga nada. Cada anotação aberta é cancelada pelo MESMO caminho do
cancelamento unitário (motivo, prazo do restaurante, autorização, auditoria) e
continua no histórico; o cartão volta livre. Cada comanda tem a própria
transação: a recusa de uma não desfaz as outras, e a resposta diz o que
aconteceu com cada uma.
"""
import pytest
from datetime import timedelta
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.orders.command_billing import attach_commands_to_order
from apps.orders.command_items import launch_item
from apps.orders.models import CommandItem, Order
from apps.orders.services import create_order
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db

URL = "/api/v1/commands/bulk-reset/"


def _comanda(restaurant, branch, numero, produto, usuario, itens=1):
    comanda = Command.objects.create(account=restaurant.account, restaurant=restaurant, branch=branch, number=numero)
    for _ in range(itens):
        launch_item(command=comanda, product=produto, user=usuario, quantity=1)
    return comanda


def _itens(comanda):
    with tenant_context(comanda.account):
        return list(CommandItem.objects.filter(command=comanda).order_by("launched_at"))


def test_zera_varias_comandas_e_guarda_o_historico(api_client, restaurant, branch, manager_user, produto):
    a = _comanda(restaurant, branch, 11, produto, manager_user, itens=2)
    b = _comanda(restaurant, branch, 12, produto, manager_user)

    resposta = api_client.post(URL, {"ids": [str(a.pk), str(b.pk)], "reason": "Fim do expediente"}, format="json")

    assert resposta.status_code == 200, resposta.content
    assert {r["number"]: r["items_removed"] for r in resposta.data["reset"]} == {11: 2, 12: 1}
    assert resposta.data["skipped"] == []
    for comanda in (a, b):
        comanda.refresh_from_db()
        assert comanda.em_uso is False
        # O histórico continua lá: cancelado, com motivo e autor.
        for item in _itens(comanda):
            assert item.status == CommandItem.STATUS_CANCELLED
            assert item.void_reason == "Fim do expediente"
            assert item.voided_by_id == manager_user.pk


def test_sem_motivo_nao_zera_nada(api_client, restaurant, branch, manager_user, produto):
    a = _comanda(restaurant, branch, 13, produto, manager_user)

    resposta = api_client.post(URL, {"ids": [str(a.pk)], "reason": "  "}, format="json")

    assert resposta.status_code == 400
    assert all(i.status != CommandItem.STATUS_CANCELLED for i in _itens(a))


def test_comanda_dentro_de_conta_aberta_fica_e_as_outras_zeram(
    api_client, contexto_tenant, restaurant, branch, manager_user, produto, sem_caixa_obrigatorio,
):
    """Cancelar o que já está numa conta aberta deixaria a conta com item fantasma."""
    na_conta = _comanda(restaurant, branch, 14, produto, manager_user)
    livre = _comanda(restaurant, branch, 15, produto, manager_user)
    conta = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COMMAND, user=manager_user)
    attach_commands_to_order(order=conta, command_ids=[na_conta.pk], user=manager_user)

    resposta = api_client.post(URL, {"ids": [str(na_conta.pk), str(livre.pk)], "reason": "Limpeza"}, format="json")

    assert [r["number"] for r in resposta.data["reset"]] == [15]
    [recusa] = resposta.data["skipped"]
    assert recusa["number"] == 14
    assert f"#{conta.sequence}" in recusa["reason"]
    assert all(i.status != CommandItem.STATUS_CANCELLED for i in _itens(na_conta))


def test_item_fora_do_prazo_precisa_de_autorizacao_e_a_comanda_volta_inteira(
    api_client, restaurant, branch, manager_user, produto,
):
    restaurant.item_cancel_window_seconds = 60
    restaurant.set_cash_action_password("4321")
    restaurant.save()
    comanda = _comanda(restaurant, branch, 16, produto, manager_user, itens=2)
    with tenant_context(restaurant.account):
        primeiro = _itens(comanda)[0]
        CommandItem.objects.filter(pk=primeiro.pk).update(
            status=CommandItem.STATUS_SENT, sent_to_kitchen_at=timezone.now() - timedelta(minutes=5)
        )

    sem = api_client.post(URL, {"ids": [str(comanda.pk)], "reason": "Limpeza"}, format="json")

    assert sem.data["reset"] == []
    assert "prazo" in sem.data["skipped"][0]["reason"]
    # Nem o item que podia sair saiu: a comanda é zerada inteira ou não é.
    assert all(i.status != CommandItem.STATUS_CANCELLED for i in _itens(comanda))

    com = api_client.post(URL, {"ids": [str(comanda.pk)], "reason": "Limpeza", "cash_password": "4321"}, format="json")

    assert [r["number"] for r in com.data["reset"]] == [16]


def test_zerar_de_novo_e_inofensivo(api_client, restaurant, branch, manager_user, produto):
    """Repetição depois de um timeout de rede não pode virar erro."""
    a = _comanda(restaurant, branch, 17, produto, manager_user)
    api_client.post(URL, {"ids": [str(a.pk)], "reason": "Limpeza"}, format="json")

    de_novo = api_client.post(URL, {"ids": [str(a.pk)], "reason": "Limpeza"}, format="json")

    assert de_novo.status_code == 200
    assert de_novo.data["reset"] == [{"id": str(a.pk), "number": 17, "items_removed": 0}]


def test_comanda_de_outra_conta_e_recusada_sem_vazar(api_client, restaurant, branch, manager_user, produto):
    a = _comanda(restaurant, branch, 18, produto, manager_user)

    resposta = api_client.post(
        URL, {"ids": [str(a.pk), "00000000-0000-0000-0000-000000000000"], "reason": "Limpeza"}, format="json"
    )

    assert [r["number"] for r in resposta.data["reset"]] == [18]
    assert resposta.data["skipped"] == [
        {"id": "00000000-0000-0000-0000-000000000000", "number": None, "reason": "Comanda não encontrada."}
    ]


def test_cozinha_so_e_avisada_do_que_ainda_esta_em_producao(
    api_client, restaurant, branch, manager_user, produto, monkeypatch,
):
    """Zerar no fim do dia não pode encher a cozinha de cupom de prato já servido."""
    import apps.printers.command_kitchen as cozinha

    avisados = []
    monkeypatch.setattr(
        cozinha, "register_command_item_cancellation_jobs", lambda *, item, user, reason: avisados.append(item.pk)
    )
    comanda = _comanda(restaurant, branch, 19, produto, manager_user, itens=2)
    em_producao, entregue = _itens(comanda)
    with tenant_context(restaurant.account):
        CommandItem.objects.filter(pk=em_producao.pk).update(status=CommandItem.STATUS_PREPARING)
        CommandItem.objects.filter(pk=entregue.pk).update(status=CommandItem.STATUS_DELIVERED)

    api_client.post(URL, {"ids": [str(comanda.pk)], "reason": "Limpeza"}, format="json")

    assert avisados == [em_producao.pk]


def test_encerramento_das_sobras_gera_evento_para_sincronizar(api_client, restaurant, branch, manager_user, produto):
    """`QuerySet.update()` não dispara sinal: o encerramento sumia da sincronização."""
    from django.db.models.signals import post_save

    vistos = []

    def ouvir(sender, instance, update_fields=None, **kwargs):
        if sender is CommandItem and update_fields and "command_status" in update_fields:
            vistos.append(instance.pk)

    comanda = _comanda(restaurant, branch, 20, produto, manager_user, itens=2)
    # A cortesia não é cobrável: não passa pelo cancelamento, é a SOBRA que o
    # cartão encerra ao ser liberado — o caminho que usava `update()`.
    cortesia = _itens(comanda)[1]
    with tenant_context(restaurant.account):
        CommandItem.objects.filter(pk=cortesia.pk).update(status=CommandItem.STATUS_COMPED)
    post_save.connect(ouvir)
    try:
        api_client.post(URL, {"ids": [str(comanda.pk)], "reason": "Limpeza"}, format="json")
    finally:
        post_save.disconnect(ouvir)

    assert cortesia.pk in vistos
