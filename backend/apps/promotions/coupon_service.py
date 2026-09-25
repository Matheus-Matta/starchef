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
from apps.promotions.coupon_identity import cliente_por_cpf, cpf_do_pedido
from apps.promotions.coupon_rules import avaliar
from apps.promotions.models import Coupon, CouponRedemption


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
    order.coupon = None
    order.coupon_code = ""
    order.coupon_discount = Decimal("0.00")
    order.save(update_fields=["coupon", "coupon_code", "coupon_discount", "updated_at"])
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


@transaction.atomic
def registrar_resgate(order):
    """Grava o resgate do cupom deste pedido — no pagamento, e uma vez só.

    Idempotente de propósito: o pagamento pode ser confirmado duas vezes (fila
    offline reenviando, webhook repetido), e um segundo resgate faria o cupom de
    compra única aparecer como usado duas vezes pela mesma pessoa.
    """
    if not order.coupon_id or Decimal(order.coupon_discount or 0) <= 0:
        return None
    existente = CouponRedemption.all_objects.filter(
        coupon_id=order.coupon_id,
        order_id=order.pk,
        deleted_at__isnull=True,
    ).first()
    if existente is not None:
        return existente
    cpf = cpf_do_pedido(order)
    cliente = order.customer or cliente_por_cpf(order.account_id, cpf)
    return CouponRedemption.objects.create(
        account_id=order.account_id,
        restaurant_id=order.restaurant_id,
        branch_id=order.branch_id,
        coupon_id=order.coupon_id,
        order_id=order.pk,
        customer=cliente,
        document=cpf,
        amount=Decimal(order.coupon_discount or 0),
    )


@transaction.atomic
def devolver_resgate(order):
    """Devolve o direito quando o pedido é cancelado ou estornado.

    Apaga o resgate em vez de decrementar um contador: contador perde a conta na
    primeira condição de corrida, e "quem usou" deixa de ser respondível.
    """
    return CouponRedemption.all_objects.filter(order_id=order.pk).delete()
