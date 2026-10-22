"""O cupom conferido contra os NÚMEROS de uma venda que ainda não existe.

A venda nova vive no PDV até a conclusão. Para dar o desconto do cupom, o PDV
simulava a venda inteira no servidor (60 a 120 consultas por cupom digitado).
As regras (`coupon_rules.avaliar`) só pedem números: subtotal de produtos,
frete, tipo do pedido, CPF e — para o cupom que não acumula — se algum produto
está em promoção. É isso que chega aqui, e o veredito é o mesmo do pedido.

A conclusão (`/orders/submit/`) aplica o cupom de verdade e confere o total:
o que esta conferência disse não é promessa, é prévia.
"""
from decimal import Decimal, InvalidOperation

from rest_framework.exceptions import ValidationError

from apps.customers.validators import strip_cpf
from apps.promotions.coupon_rules import avaliar


def _valor(dados, campo):
    try:
        valor = Decimal(str(dados.get(campo) or "0"))
    except (InvalidOperation, ValueError):
        raise ValidationError({campo: "Valor inválido."}) from None
    if valor < 0:
        raise ValidationError({campo: "Valor inválido."})
    return valor


def _tem_item_em_promocao(product_ids, restaurant_id):
    from apps.menu.models import Product
    from apps.promotions.pricing import primar

    produtos = list(Product.objects.filter(pk__in=[str(p) for p in product_ids or []]))
    if not produtos:
        return False
    primar(produtos, restaurant_id=restaurant_id)
    # A mesma pergunta de `coupon_service._tem_item_em_promocao`: promoção de
    # TABELA ativa, e não o promocional manual do cadastro.
    return any(p.active_promotion is not None for p in produtos)


def avaliar_venda(cupom, *, account_id, dados):
    """`(motivo, desconto, cliente)` do cupom para a venda descrita em `dados`."""
    if dados.get("subtotal") in (None, ""):
        raise ValidationError({"subtotal": "Informe o pedido ou o subtotal da venda."})
    itens_em_promocao = False
    if not cupom.combines_with_promotions:
        itens_em_promocao = _tem_item_em_promocao(dados.get("products"), dados.get("restaurant"))
    return avaliar(
        cupom,
        account_id=account_id,
        subtotal=_valor(dados, "subtotal"),
        delivery_fee=_valor(dados, "delivery_fee"),
        order_type=dados.get("order_type") or "",
        cpf=strip_cpf(str(dados.get("cpf") or "")),
        itens_em_promocao=itens_em_promocao,
    )
