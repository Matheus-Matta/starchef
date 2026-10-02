"""Rateio do desconto da NFC-e entre os itens, com teto por item.

O rateio comum (`FocusNfeProvider._allocate_total`) joga a sobra de centavos
no ÚLTIMO item. Com um item barato no fim e um desconto alto, esse item ficava
com desconto maior que o próprio valor — e a SEFAZ rejeita `vDesc > vProd`.
Achado por força bruta: 12 em 200 mil vendas aleatórias.

Aqui cada item tem teto, e o que passar dele vai para os itens que ainda
comportam, do mais caro para o mais barato. A soma continua exata;
`_validate_totals` já garante desconto <= produtos.
"""
from decimal import ROUND_HALF_UP, Decimal

DUAS_CASAS = Decimal("0.01")


def _proporcional(itens, total):
    produtos = sum((item.total_price for item in itens), start=Decimal("0.00"))
    rateio, distribuido = {}, Decimal("0.00")
    for item in itens[:-1]:
        parte = (total * item.total_price / produtos).quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)
        parte = min(parte, total - distribuido)
        rateio[item.pk] = parte
        distribuido += parte
    rateio[itens[-1].pk] = total - distribuido
    return rateio


def _recusar(mensagem):
    # Import aqui: `FiscalRejection` mora em `providers.py`, que importa este módulo.
    from apps.invoices.providers import FiscalRejection

    raise FiscalRejection(mensagem)


def ratear_desconto(itens, total):
    total = Decimal(total).quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)
    if not total:
        return {}
    if sum((item.total_price for item in itens), start=Decimal("0.00")) <= 0:
        _recusar("Focus NFe: nao e possivel ratear valores em uma nota sem produtos.")
    proporcional = _proporcional(itens, total)
    rateio = {item.pk: max(min(proporcional[item.pk], item.total_price), Decimal("0.00")) for item in itens}
    sobra = total - sum(rateio.values(), start=Decimal("0.00"))
    for item in sorted(itens, key=lambda i: i.total_price, reverse=True):
        if sobra <= 0:
            break
        extra = min(item.total_price - rateio[item.pk], sobra)
        if extra > 0:
            rateio[item.pk] += extra
            sobra -= extra
    if sobra > 0:
        _recusar("Focus NFe: o desconto é maior que o valor dos produtos.")
    return rateio
