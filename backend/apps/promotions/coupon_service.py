"""Aplicar, reavaliar e retirar o cupom de um pedido.

O CUPOM É REAVALIADO A CADA RECÁLCULO. Quem aplica um cupom de "acima de R$ 50"
num pedido de R$ 60 e depois remove metade dos itens não pode continuar com o
desconto: o pedido deixou de se qualificar. Congelar o abatimento no momento da
aplicação é como se dá desconto sem querer — e ninguém revisa um total que já
apareceu certo na tela uma vez.

O RESGATE SÓ EXISTE QUANDO O PEDIDO É PAGO. Antes disso o cupom está apenas
reservado no pedido; gravar o resgate na aplicação faria um cupom de compra
única queimar em um pedido abandonado, e o cliente perderia o direito sem ter
comprado nada.
"""

from decimal import Decimal

from django.db import transaction

from apps.core.api_errors import CouponRejected
from apps.promotions.coupon_guards import (
    recusar_pedido_encerrado,
    recusar_se_o_total_ficar_abaixo_do_recebido,
)
from apps.promotions.coupon_identity import cpf_do_pedido
from apps.promotions.coupon_rules import avaliar
from apps.promotions.models import Coupon


def _base_do_cupom(order):
    """O subtotal que o cupom olha: PRODUTOS, sem taxa de serviço e sem entrega.

    `order.subtotal` já é a soma dos itens não cancelados, e as taxas moram em
    campos próprios. É esta separação que permite cumprir a regra ao pé da
    letra sem recalcular nada.
    """
    return Decimal(order.subtotal or 0)


def _tem_item_em_promocao(order):
    """O pedido carrega algum item cujo produto está em promoção agora?

    Só é consultado por cupom que não acumula — não vale pagar a consulta em
    todo pedido para responder uma pergunta que quase nenhum cupom faz.
    """
    from apps.promotions.pricing import primar

    produtos = [item.product for item in order.items.select_related("product") if item.product_id]
    if not produtos:
        return False
    primar(produtos, restaurant_id=order.restaurant_id)
    return any(p.active_promotion is not None for p in produtos)


def avaliar_no_pedido(coupon, order):
    """`(motivo, desconto, cliente)` deste cupom neste pedido, agora."""
    precisa_combinar = not coupon.combines_with_promotions
    return avaliar(
        coupon,
        account_id=order.account_id,
        subtotal=_base_do_cupom(order),
        delivery_fee=Decimal(order.delivery_fee or 0),
        order_type=order.order_type,
        cpf=cpf_do_pedido(order),
        itens_em_promocao=_tem_item_em_promocao(order) if precisa_combinar else False,
    )


def buscar_cupom(account_id, codigo):
    """O cupom pelo código, sem escopo de request.

    `all_objects` com a conta explícita porque isto também roda a partir da fila
    offline do PDV e da sincronização, onde o manager escopado devolveria vazio
    — e "cupom não encontrado" para um cupom que existe é o pior erro possível
    na frente do cliente.
    """
    codigo = (codigo or "").strip().upper()
    if not codigo:
        raise CouponRejected("Informe o código do cupom.")
    cupom = Coupon.all_objects.filter(
        account_id=account_id,
        code=codigo,
        deleted_at__isnull=True,
    ).first()
    if cupom is None:
        raise CouponRejected(f'Não existe cupom com o código "{codigo}".')
    return cupom


@transaction.atomic
def aplicar_cupom(order, codigo):
    """Prende o cupom ao pedido. Recusa com o motivo quando não se aplica."""
    recusar_pedido_encerrado(order)
    cupom = buscar_cupom(order.account_id, codigo)
    motivo, desconto, _cliente = avaliar_no_pedido(cupom, order)
    if motivo:
        raise CouponRejected(motivo)
    order.coupon = cupom
    order.coupon_code = cupom.code
    order.coupon_discount = desconto
    order.save(update_fields=["coupon", "coupon_code", "coupon_discount", "updated_at"])
    return cupom, desconto


@transaction.atomic
def retirar_cupom(order):
    """Solta o cupom. O código sai também: o pedido não tem mais cupom nenhum."""
    recusar_pedido_encerrado(order)
    order.coupon = None
    order.coupon_code = ""
    order.coupon_discount = Decimal("0.00")
    order.save(update_fields=["coupon", "coupon_code", "coupon_discount", "updated_at"])
    return order


@transaction.atomic
def mexer_no_cupom(order, codigo):
    """Aplica, troca ou retira o cupom — e devolve o pedido recalculado.

    É o que a TELA DE PAGAMENTO chama. Ela precisa de três garantias que
    `aplicar_cupom` sozinho não dá:

    1. o total tem de vir já refeito, porque o teclado do caixa desenha o troco
       a partir dele — devolver o pedido antigo faria o operador cobrar o valor
       de antes do desconto;
    2. a conferência do que já foi recebido só é possível DEPOIS do recálculo;
    3. tudo numa transação: a recusa do item 2 tem de desfazer a aplicação, ou o
       pedido ficaria com o desconto que acabou de ser rejeitado.

    `codigo` vazio RETIRA. É gesto de uma tecla só no caixa, e separar em duas
    rotas faria a tela decidir qual chamar a partir de um campo de texto.
    """
    from apps.orders.services import recalculate_order

    if str(codigo or "").strip():
        aplicar_cupom(order, codigo)
    else:
        retirar_cupom(order)
    order = recalculate_order(order)
    recusar_se_o_total_ficar_abaixo_do_recebido(order)
    return order


def revalidar(order):
    """Reconfere o cupom do pedido e devolve o desconto que vale AGORA.

    Devolve `(desconto, motivo_da_queda)`. Quando o pedido deixa de se
    qualificar, o desconto vira zero e o motivo volta para quem chamou poder
    AVISAR — um cupom que desaparece sem explicação faz o operador achar que o
    sistema comeu o desconto e aplicar um à mão por cima.

    O vínculo com o cupom NÃO é apagado aqui: o pedido pode voltar a se
    qualificar no item seguinte, e reaplicar sozinho é melhor do que obrigar o
    caixa a digitar o código de novo.
    """
    if not order.coupon_id:
        return Decimal("0.00"), None
    motivo, desconto, _cliente = avaliar_no_pedido(order.coupon, order)
    if motivo:
        return Decimal("0.00"), motivo
    return desconto, None

# O RESGATE mora em `coupon_redemption.py`: ele nasce no pagamento e morre no
# cancelamento, e nao tem nada a ver com aplicar cupom numa conta aberta.
from apps.promotions.coupon_redemption import (  # noqa: E402,F401
    devolver_resgate,
    registrar_resgate,
)
