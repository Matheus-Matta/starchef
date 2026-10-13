"""A venda inteira num envio só: pedido, itens, comandas e recebimentos.

O PDV monta a venda na memória e manda UM payload quando ela precisa existir:
na cozinha, no "pagar depois" ou no "concluir" (com os recebimentos juntos).
Antes eram uma chamada para criar o pedido, uma por item, uma para anexar as
comandas e uma por recebimento — e uma troca loja/nuvem no meio deixava
metade da venda em cada servidor.

Tudo numa transação: entra inteiro ou não entra. E tudo com o UUID que o PDV
deu, então o reenvio (rede caiu, desvio para a nuvem, "pagar depois" e depois
pagar) acrescenta só o que é novo e devolve a mesma venda — nunca duplica:

* pedido: o UUID do corpo; existindo, é o mesmo pedido;
* item: o UUID da linha; existindo, já foi lançado;
* comanda: anexa só o que ela ainda tem A COBRAR fora deste pedido — e, com
  `command_items`, só as anotações que o caixa VIU (o lançado depois fica para
  a próxima conta); o item que nasce da anotação tem UUID calculado;
* recebimento: `register_payment` com o UUID (`recebimento_por_uuid.py`).

`simular=True` faz tudo e desfaz no fim: é o total oficial (taxa, promoção,
cupom) para a tela de pagamento, sem gravar nada. Tempo real e notificações
saem em `on_commit`, então nada escapa da simulação.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core import uuid_do_aparelho
from apps.core.audit import auditoria_em_lote
from apps.orders.venda_inteira_itens import lancar_itens
from apps.synchronization.services import outbox_lote
from apps.core.tenant import tenant_context
from apps.orders.conflitos import ConflitoComDestino
from apps.orders.models import Order, OrderItem
from apps.orders.venda_inteira_partes import conferir_total, receber

TIPOS = {Order.TYPE_COUNTER, Order.TYPE_COMMAND, Order.TYPE_DELIVERY, Order.TYPE_TAKEAWAY}


class VendaEmConflito(Exception):
    """O corpo está certo; o estado é que não aceita (409, não 400)."""


def executar(*, restaurant, user, dados, responder, simular=False, terminal=None,
             installation_id="", autorizar_desconto=None):
    """Grava (ou simula) a venda e devolve `responder(pedido, recebimentos, nova)`.

    `responder` roda DENTRO da transação: na simulação é a única chance de ler
    o pedido antes de ele ser desfeito.
    """
    order_id = uuid_do_aparelho.ler(dados.get("id"), "pedido")
    if order_id is None:
        raise ValidationError("Informe o identificador do pedido.")
    # A captura da sincronização da venda sai junta no fim, ainda nesta
    # transação; na simulação, que é desfeita, nem é montada (`outbox_lote`).
    captura = outbox_lote.descartando() if simular else outbox_lote.em_lote()
    with tenant_context(restaurant.account), transaction.atomic():
        # A auditoria por dentro: sai antes da captura, que sincroniza também
        # os registros dela.
        with captura, auditoria_em_lote(descartar=simular):
            pedido, nova = _pedido(restaurant, user, order_id, dados)
            lancar_itens(pedido, user, dados.get("items") or [])
            _comandas(pedido, user, dados.get("commands") or [], nova, dados.get("command_items"))
            _cozinha(pedido, user, dados.get("kitchen"))
            _fechar(pedido, user, dados.get("close"), autorizar_desconto)
            if not simular:
                conferir_total(pedido, dados)
            recebimentos = [] if simular else receber(
                pedido, user, dados.get("payments") or [], terminal, installation_id)
        pedido.refresh_from_db()
        resposta = responder(pedido, recebimentos, nova)
        if simular:
            transaction.set_rollback(True)
    return resposta


def _pedido(restaurant, user, order_id, dados):
    from apps.orders.services import create_order

    existente = Order.all_objects.select_for_update(of=("self",)).filter(pk=order_id).first()
    if existente is not None:
        if existente.restaurant_id != restaurant.pk or existente.deleted_at is not None:
            raise VendaEmConflito("Este pedido não pode mais ser alterado: atualize a tela.")
        return existente, False
    tipo = dados.get("order_type") or Order.TYPE_COUNTER
    if dados.get("commands"):
        tipo = Order.TYPE_COMMAND
    if tipo not in TIPOS:
        raise ValidationError("Tipo de pedido inválido.")
    extras = {"customer_id": dados["customer"]} if dados.get("customer") else {}
    return create_order(restaurant=restaurant, order_type=tipo, user=user, id=order_id,
                        metafields=dados.get("metafields"), **extras), True


def _comandas(pedido, user, comandas, nova, vistas=None):
    from apps.orders.command_billing import attach_commands_to_order

    if not comandas:
        return
    if not nova:
        # Reenvio ou "pagar depois": só a comanda que ainda tem o que cobrar
        # FORA deste pedido. A que já está toda aqui (ou já foi paga) é a
        # mesma venda chegando de novo, não "nada a cobrar".
        neste = set(OrderItem.objects.filter(order=pedido).exclude(command_item=None)
                    .values_list("command_item_id", flat=True))
        comandas = [c for c in comandas
                    if set(_cobraveis(c, vistas)) - neste]
        if not comandas:
            return
    try:
        attach_commands_to_order(order=pedido, command_ids=comandas, user=user, only_items=vistas)
    except ConflitoComDestino:
        raise  # já diz para onde o PDV deve ir
    except ValidationError as exc:
        raise VendaEmConflito(" ".join(exc.messages)) from exc


def _cozinha(pedido, user, envio):
    """Manda à produção o que está pendente — o F9, no mesmo envio.

    Sem pendente (reenvio, ou tudo já foi), não manda nada de novo.
    """
    if not envio or not OrderItem.objects.filter(order=pedido, status=OrderItem.STATUS_PENDING).exists():
        return
    from apps.orders.services import send_order_to_kitchen

    send_order_to_kitchen(pedido, user, client_batch_serial=envio.get("client_batch_serial"),
                          offline_printed=bool(envio.get("offline_printed")))


def _fechar(pedido, user, fechamento, autorizar_desconto=None):
    """Taxa, desconto, CPF/CNPJ e cupom — o `/close/`, no mesmo envio.

    Ia à parte antes de pagar: mais uma chamada que podia cair do outro lado
    numa troca loja/nuvem. Pedido já pago não se fecha de novo (reenvio).
    """
    if not fechamento:
        return
    from apps.orders.services import close_order

    pedido.refresh_from_db()
    if pedido.payment_status == Order.PAYMENT_PAID:
        return
    close_order(
        pedido, user, marcar_aguardando=True,
        discount=fechamento.get("discount", 0),
        service_fee=fechamento.get("service_fee"),
        service_fee_enabled=fechamento.get("service_fee_enabled"),
        fiscal_customer_cpf=fechamento.get("fiscal_customer_cpf"),
        fiscal_customer_cnpj=fechamento.get("fiscal_customer_cnpj"),
        expected_total=fechamento.get("expected_total"),
        coupon_code=fechamento.get("coupon_code"),
        # A senha de ações do caixa (ou o login de quem libera) vem no corpo
        # da venda, como no `/close/`: sem repassá-la, o caixa que não é
        # gerente nunca conseguia dar desconto numa venda nova.
        authorize_discount=autorizar_desconto,
    )


def _cobraveis(comanda, vistas):
    from apps.orders.command_billing import billable_items_of

    pendentes = billable_items_of([comanda])
    if vistas is not None:
        pendentes = pendentes.filter(pk__in=list(vistas))
    return pendentes.values_list("pk", flat=True)
