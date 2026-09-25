"""As regras do cupom, cada uma devolvendo o MOTIVO em português.

Uma função por regra, e todas devolvendo texto em vez de `False`. A razão é a
conversa que acontece no caixa: o cliente está ouvindo, e "cupom inválido" faz
o operador repetir a digitação três vezes para um cupom que simplesmente venceu
ontem. O motivo é o que encerra a discussão.

A ORDEM IMPORTA. Primeiro o que é do cupom (venceu, esgotou), depois o que é do
pedido (valor mínimo, tipo), e por último o que é da pessoa (CPF, grupo, uso
anterior) — porque a última é a única que obriga a pedir um dado ao cliente, e
pedir CPF para depois dizer "esse cupom venceu" é o pior dos roteiros.
"""

from decimal import Decimal

from django.utils import timezone

from apps.promotions.coupon_identity import (
    cliente_por_cpf,
    ja_comprou,
    usos_da_pessoa,
    usos_do_cupom,
)

MOEDA = "R$ {:,.2f}"


def _reais(valor):
    return MOEDA.format(Decimal(valor or 0)).replace(",", "X").replace(".", ",").replace("X", ".")


def _motivo_da_janela(coupon):
    if not coupon.is_enabled:
        return "Este cupom está desativado."
    agora = timezone.now()
    if coupon.starts_at and agora < coupon.starts_at:
        return f"Este cupom começa a valer em {timezone.localtime(coupon.starts_at):%d/%m/%Y às %H:%M}."
    if coupon.ends_at and agora > coupon.ends_at:
        return f"Este cupom venceu em {timezone.localtime(coupon.ends_at):%d/%m/%Y}."
    return None


def _motivo_do_esgotamento(coupon):
    if coupon.usage_limit and usos_do_cupom(coupon) >= coupon.usage_limit:
        return "Este cupom já atingiu o limite de usos."
    return None


def _motivo_do_pedido(coupon, subtotal, order_type):
    """Valor mínimo e tipo de pedido.

    O MÍNIMO É SOBRE PRODUTOS, sem taxa de serviço e sem entrega — quem chama
    esta função passa o subtotal já limpo. Somar as taxas liberaria o cupom de
    "acima de R$ 50" num pedido de R$ 44 de comida que virou 50 por causa do
    frete, premiando uma venda que nunca alcançou o patamar.
    """
    if coupon.minimum_order_value and Decimal(subtotal or 0) < Decimal(coupon.minimum_order_value):
        return (
            f"Este cupom vale a partir de {_reais(coupon.minimum_order_value)} em produtos "
            "(sem taxa de serviço e sem entrega)."
        )
    aceitos = coupon.order_types or []
    if aceitos and order_type and order_type not in aceitos:
        return "Este cupom não vale para este tipo de pedido."
    return None


def _e_restrito(coupon):
    """O cupom aponta pessoas ou grupos? Então CPF deixa de ser opcional."""
    return coupon.customers.exists() or coupon.customer_groups.exists()


def _motivo_da_pessoa(coupon, account_id, cpf):
    """Tudo que depende de saber QUEM é: CPF, grupo, cliente, uso anterior.

    Devolve `(motivo, cliente)`: o cliente resolvido volta para quem chamou
    gravar no resgate, evitando resolver o mesmo CPF duas vezes.
    """
    restrito = _e_restrito(coupon)
    if not cpf:
        if coupon.requires_document:
            return "Este cupom exige o CPF do cliente na nota.", None
        if restrito:
            return "Este cupom é de clientes específicos — informe o CPF para conferir.", None
        if coupon.first_purchase_only or coupon.limite_por_cliente:
            return "Este cupom é limitado por cliente — informe o CPF na nota.", None
        return None, None

    cliente = cliente_por_cpf(account_id, cpf)

    if restrito:
        if cliente is None:
            return "Este CPF não está na lista de clientes deste cupom.", None
        proprio = coupon.customers.filter(pk=cliente.pk).exists()
        por_grupo = coupon.customer_groups.filter(customers__pk=cliente.pk).exists()
        if not proprio and not por_grupo:
            return "Este cliente não participa dos grupos deste cupom.", cliente

    limite = coupon.limite_por_cliente
    if limite and usos_da_pessoa(coupon, cpf, cliente) >= limite:
        if limite == 1:
            return "Este CPF já usou este cupom — ele vale uma vez por cliente.", cliente
        return f"Este CPF já usou este cupom {limite} vezes, o limite dele.", cliente

    if coupon.first_purchase_only and ja_comprou(account_id, cpf, cliente):
        return "Este cupom é só para a primeira compra, e este CPF já tem pedido pago.", cliente

    return None, cliente


def _motivo_da_combinacao(coupon, itens_em_promocao):
    if coupon.combines_with_promotions:
        return None
    if itens_em_promocao:
        return "Este cupom não acumula com promoção, e o pedido já tem item em promoção."
    return None


def avaliar(coupon, *, account_id, subtotal, delivery_fee, order_type, cpf, itens_em_promocao=False):
    """O veredito completo: `(motivo_da_recusa, desconto, cliente)`.

    `motivo` `None` significa aprovado. O desconto vem junto porque calculá-lo
    depois exigiria repetir as mesmas contas, e um cupom aprovado que desconta
    zero é uma aprovação que não serve para nada — por isso ele também recusa.
    """
    for motivo in (
        _motivo_da_janela(coupon),
        _motivo_do_esgotamento(coupon),
        _motivo_do_pedido(coupon, subtotal, order_type),
        _motivo_da_combinacao(coupon, itens_em_promocao),
    ):
        if motivo:
            return motivo, Decimal("0.00"), None

    motivo, cliente = _motivo_da_pessoa(coupon, account_id, cpf)
    if motivo:
        return motivo, Decimal("0.00"), cliente

    desconto = coupon.desconto_para(subtotal, delivery_fee)
    if desconto <= 0:
        if coupon.discount_kind == coupon.KIND_FREE_DELIVERY:
            return "Este pedido não tem taxa de entrega para o cupom abater.", Decimal("0.00"), cliente
        return "Este cupom não gera desconto neste pedido.", Decimal("0.00"), cliente
    return None, desconto, cliente
