"""Quem está pedindo o cupom — e quantas vezes já pediu.

A IDENTIDADE É O CPF. É o mesmo CPF que vai na nota, informado no pedido, e é o
único dado que o caixa realmente tem na mão quando o cliente diz o código. Um
"cliente selecionado" à parte seria uma segunda verdade: a pessoa cadastrada
como Maria e o CPF digitado no balcão podem não ser a mesma, e o cupom de
"compra única" perderia o sentido no primeiro cadastro duplicado.

Por isso o resgate guarda o CPF, e não só o vínculo com o cliente: quem volta
com um cadastro novo e o mesmo CPF continua sendo a mesma pessoa.
"""

from apps.customers.models import Customer
from apps.customers.validators import strip_cpf


def cpf_do_pedido(order):
    """O CPF da nota, só os dígitos. String vazia quando não houver."""
    return strip_cpf(getattr(order, "fiscal_customer_cpf", "") or "")


def cliente_por_cpf(account_id, cpf):
    """O cliente cadastrado com este CPF, se existir.

    `all_objects` com a conta explícita: isto também roda fora de request
    (sincronização, tarefa), onde o manager escopado devolveria vazio e o cupom
    de grupo recusaria quem tinha direito.

    A comparação é em Python porque o cadastro guarda o CPF FORMATADO
    ("123.456.789-00") e o pedido guarda só dígitos — um `filter(document=cpf)`
    nunca casaria. O `__contains` estreita a varredura antes disso.
    """
    cpf = strip_cpf(cpf or "")
    if not cpf:
        return None
    candidatos = Customer.all_objects.filter(
        account_id=account_id,
        deleted_at__isnull=True,
        document__contains=cpf[:3],
    )
    for candidato in candidatos:
        if strip_cpf(candidato.document) == cpf:
            return candidato
    return None


def usos_do_cupom(coupon):
    """Quantas vezes o cupom já foi resgatado, no total."""
    from apps.promotions.models import CouponRedemption

    return CouponRedemption.all_objects.filter(coupon_id=coupon.pk, deleted_at__isnull=True).count()


def usos_da_pessoa(coupon, cpf, customer=None):
    """Quantas vezes ESTA pessoa já resgatou o cupom.

    Conta por CPF **ou** por cliente, unindo os dois: um resgate antigo pode ter
    ficado gravado só com o cliente (pedido sem CPF na nota), e um recente só
    com o CPF (venda de balcão sem cadastro). Contar apenas um dos dois daria
    uma segunda chance a quem já usou.
    """
    from django.db.models import Q

    from apps.promotions.models import CouponRedemption

    cpf = strip_cpf(cpf or "")
    if not cpf and customer is None:
        return 0
    condicao = Q(pk__in=[])
    if cpf:
        condicao |= Q(document=cpf)
    if customer is not None:
        condicao |= Q(customer_id=customer.pk)
    return (
        CouponRedemption.all_objects.filter(coupon_id=coupon.pk, deleted_at__isnull=True)
        .filter(condicao)
        .count()
    )


def ja_comprou(account_id, cpf, customer=None):
    """Esta pessoa já tem pedido pago? É o que "primeira compra" pergunta.

    Olha o pedido PAGO, e não qualquer pedido: um pedido aberto e abandonado não
    é uma compra, e tratá-lo como tal tiraria o cupom de boas-vindas de quem
    ainda não comprou nada.
    """
    from django.db.models import Q

    from apps.orders.models import Order

    cpf = strip_cpf(cpf or "")
    condicao = Q(pk__in=[])
    if cpf:
        condicao |= Q(fiscal_customer_cpf=cpf)
    if customer is not None:
        condicao |= Q(customer_id=customer.pk)
    if not cpf and customer is None:
        return False
    return (
        Order.all_objects.filter(
            account_id=account_id,
            deleted_at__isnull=True,
            status=Order.STATUS_PAID,
        )
        .filter(condicao)
        .exists()
    )
