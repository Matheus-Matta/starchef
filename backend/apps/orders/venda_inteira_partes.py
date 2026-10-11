"""Os pedaços da venda inteira que não são pedido: pesagem, total e recebimentos.

Ver `venda_inteira.py`. Ficam aqui para cada arquivo ter um assunto.
"""
from django.core.exceptions import ValidationError

from apps.orders.conflitos import ConflitoComDestino, destino
from apps.orders.models import Order, OrderItem


def leitura_da_balanca(pedido, leitura_id):
    if not leitura_id:
        return None
    from apps.printers.models import ScaleReading

    leitura = ScaleReading.objects.select_related("scale").filter(
        pk=leitura_id, account=pedido.account).first()
    if leitura is None:
        raise ValidationError("Leitura de balança não encontrada.")
    return leitura


def receber(pedido, user, entradas, terminal, installation_id):
    from apps.payments import recebimento_por_uuid
    from apps.payments.services import register_payment

    from apps.orders.models import Order
    from apps.payments.models import Payment

    feitos = []
    for entrada in entradas:
        if not entrada.get("payment_method") or entrada.get("amount") in (None, ""):
            raise ValidationError("Cada recebimento precisa de forma e valor.")
        pagamento_id = recebimento_por_uuid.ler_id(entrada.get("id"))
        pedido.refresh_from_db(fields=["payment_status"])
        if (pedido.payment_status == Order.PAYMENT_PAID and pagamento_id is not None
                and not Payment.all_objects.filter(pk=pagamento_id).exists()):
            # A venda chegou aqui de novo depois de o pedido PAGO ter chegado
            # pela sincronização, mas antes do recebimento dele. É a mesma
            # venda: responder "já foi pago" com erro era errado. O que chegou
            # fica no histórico (`SyncDiscard`).
            _guardar_em_pedido_pago(pedido, pagamento_id, entrada, user)
            continue
        metadata = dict(entrada.get("metadata") or {})
        if entrada.get("card_subtype"):
            metadata["card_subtype"] = entrada["card_subtype"]
        feitos.append(register_payment(
            order=pedido, user=user, payment_method_id=entrada["payment_method"],
            amount=entrada["amount"], idempotency_key=entrada.get("idempotency_key"),
            metadata=metadata, cash_register_id=entrada.get("cash_register"),
            terminal=terminal, installation_id=installation_id,
            payment_id=pagamento_id,
            client_updated_at=recebimento_por_uuid.ler_horario(entrada.get("client_updated_at")),
        ))
    return feitos


def _guardar_em_pedido_pago(pedido, pagamento_id, entrada, user):
    from apps.synchronization.models import SyncDiscard
    from apps.synchronization.services import descartes

    descartes.registrar(
        origem=SyncDiscard.ORIGEM_API, motivo=SyncDiscard.MOTIVO_REENVIO,
        entity_type="payment", entity_id=pagamento_id, account_id=pedido.account_id,
        dados={**entrada, "order": str(pedido.pk), "observacao": "pedido já pago aqui"},
        usuario=user,
    )


def conferir_total(pedido, dados):
    """O total que o caixa MOSTROU ao cliente tem de ser o da conta agora.

    Entre simular e concluir, parte da comanda pode ter sido cobrada em outra
    conta: o total caía e o caixa recebia pelo valor velho. Diferente, a venda
    é recusada (409) sem gravar — dizendo onde o resto foi cobrado, para o PDV
    explicar. Pedido já pago (reenvio) não é conferido.
    """
    esperado = dados.get("expected_total")
    if esperado in (None, ""):
        return
    from apps.core.numbers import parse_money

    pedido.refresh_from_db(fields=["total", "payment_status"])
    if pedido.payment_status == Order.PAYMENT_PAID:
        return
    mostrado = parse_money(esperado, field="expected_total")
    if pedido.total == mostrado:
        return
    cobradas = OrderItem.all_objects.exclude(order_id=pedido.pk).filter(
        **({"command_item_id__in": dados["command_items"]} if dados.get("command_items")
           else {"command_id__in": dados.get("commands") or []}),
    ).values_list("order_id", flat=True).distinct()[:5]
    raise ConflitoComDestino(
        f"O total mudou: a tela mostrou {_reais(mostrado)} e a conta agora é "
        f"{_reais(pedido.total)}. Confira antes de receber.",
        code="total_mudou", expected_total=mostrado, total=pedido.total,
        cobradas_em=[destino(conta) for conta in cobradas],
    )


def _reais(valor):
    return f"R$ {valor:.2f}".replace(".", ",")
